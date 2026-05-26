from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, Settings
from .http_client import HttpJsonClient
from .ilp import QuestIlpWriter
from .questdb import SYMBOL_COLUMNS, TIMESTAMP_COLUMNS, QuestSqlClient
from .redis_client import MinimalRedis
from .tdx import TdxClient, extract_list, unwrap_payload
from .time_utils import minute_key, now_cn, parse_datetime, yyyymmdd
from .transform import (
    INTRADAY_TYPES,
    day_start,
    infer_asset_type,
    normalize_bar,
    normalize_instrument,
    normalize_minute,
    normalize_quote,
    normalize_trade,
    orderbook_feature,
    snapshot_from_instrument,
)


logger = logging.getLogger(__name__)


class MarketIngestionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.tdx = TdxClient(
            HttpJsonClient(
                settings.tdx_api_base_url,
                timeout=settings.http_timeout_seconds,
                retries=settings.http_retries,
                backoff=settings.http_backoff_seconds,
            )
        )
        self.sql = QuestSqlClient(settings)
        self.ilp = QuestIlpWriter(settings.questdb_ilp_host, settings.questdb_ilp_port, settings.http_timeout_seconds)
        self.redis = MinimalRedis(
            settings.redis_host,
            settings.redis_port,
            settings.redis_db,
            password=settings.redis_password,
            timeout=settings.http_timeout_seconds,
        )

    def init_schema(self, schema_path: Path | None = None) -> int:
        path = schema_path or PROJECT_ROOT / "sql" / "questdb_schema.sql"
        count = self.sql.execute_file(path)
        logger.info("schema_initialized", extra={"statement_count": count, "schema_path": str(path)})
        return count

    def health(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        try:
            tdx = self.tdx.health()
            result["tdx"] = {"ok": True, "latency_ms": tdx.latency_ms, "data": tdx.data}
        except Exception as exc:
            result["tdx"] = {"ok": False, "error": str(exc)}
        try:
            self.sql.execute("SELECT 1")
            result["questdb_sql"] = {"ok": True}
        except Exception as exc:
            result["questdb_sql"] = {"ok": False, "error": str(exc)}
        try:
            result["redis"] = {"ok": self.redis.ping()}
        except Exception as exc:
            result["redis"] = {"ok": False, "error": str(exc)}
        return result

    def collect_instruments(self, exchange: str | None = None, include_etf: bool = True) -> int:
        collected_at = now_cn()
        rows: list[dict[str, Any]] = []
        stock_result = self.tdx.codes(exchange=exchange)
        stocks = extract_list(stock_result.data)
        rows.extend(normalize_instrument(item, collected_at, self.settings.source, "stock") for item in stocks if isinstance(item, dict))
        self.log_ingestion("/api/codes", f"exchange={exchange or ''}", "success" if stocks else "empty", stock_result.latency_ms, len(stocks))
        if include_etf:
            try:
                etf_result = self.tdx.etf_codes()
                etfs = extract_list(etf_result.data)
                rows.extend(normalize_instrument({"code": item} if isinstance(item, str) else item, collected_at, self.settings.source, "etf") for item in etfs)
                self.log_ingestion("/api/etf-codes", "all", "success" if etfs else "empty", etf_result.latency_ms, len(etfs))
            except Exception as exc:
                self.log_ingestion("/api/etf-codes", "all", "failed", 0, 0, str(exc))
                logger.warning("collect_etf_failed", extra={"error": str(exc)})
        rows = [row for row in rows if row.get("code")]
        self.write_table("instrument", rows)
        today = yyyymmdd(collected_at)
        snapshots = [snapshot_from_instrument(row, today) for row in rows]
        self.write_table("instrument_daily_snapshot", snapshots)
        self.checkpoint("/api/codes", "", "stock", "instrument", "", "", collected_at, today, "success")
        return len(rows)

    def collect_calendar(self, start: str, end: str) -> int:
        result = self.tdx.workday_range(start, end)
        items = extract_list(result.data)
        rows = []
        for item in items:
            if isinstance(item, str):
                date_value = item
                is_workday = True
            else:
                date_value = str(item.get("date") or item.get("Date") or item.get("day") or "")
                is_workday = bool(item.get("is_workday", item.get("isWorkday", item.get("workday", True))))
            if date_value:
                trade_date = yyyymmdd(date_value)
                rows.append({"ts": day_start(trade_date), "date_numeric": trade_date, "is_trading_day": is_workday, "source": self.settings.source})
        self.write_table("trading_calendar", rows)
        self.log_ingestion("/api/workday/range", f"{start}:{end}", "success" if rows else "empty", result.latency_ms, len(rows))
        return len(rows)

    def collect_quotes(self, codes: list[str]) -> tuple[int, int]:
        result = self.tdx.batch_quote(codes)
        items = extract_list(result.data)
        collected_at = now_cn()
        quotes = [normalize_quote(item, collected_at, self.settings.source, self.settings.price_scale) for item in items if isinstance(item, dict)]
        features = [orderbook_feature([row]) for row in quotes]
        self.write_table("quote_snapshot_1m", quotes)
        self.write_table("orderbook_feature_1m", features)
        self.log_ingestion("/api/batch-quote", f"codes={len(codes)}", "success" if quotes else "empty", result.latency_ms, len(quotes))
        return len(quotes), len(features)

    def sample_watchlist(self, codes: list[str]) -> int:
        result = self.tdx.batch_quote(codes)
        items = extract_list(result.data)
        collected_at = now_cn()
        rows = [normalize_quote(item, collected_at, self.settings.source, self.settings.price_scale) for item in items if isinstance(item, dict)]
        for row in rows:
            key = self.redis_key(row["code"], minute_key(row["ts"]))
            self.redis.rpush(key, json.dumps(row, ensure_ascii=False, default=_json_default))
            self.redis.expire(key, self.settings.quote_redis_ttl_seconds)
        self.log_ingestion("/api/batch-quote", f"watchlist={len(codes)}", "success" if rows else "empty", result.latency_ms, len(rows))
        return len(rows)

    def flush_watchlist(self, minute: str | None = None, codes: list[str] | None = None, delete_keys: bool = True) -> tuple[int, int]:
        if minute and codes:
            keys = [self.redis_key(code, minute) for code in codes]
        elif minute:
            keys = self.redis.scan_match(f"{self.settings.redis_key_prefix}:{self.settings.source}:*:{minute}")
        else:
            keys = self.redis.scan_match(f"{self.settings.redis_key_prefix}:{self.settings.source}:*")
        quotes: list[dict[str, Any]] = []
        features: list[dict[str, Any]] = []
        flushed_keys: list[str] = []
        for key in keys:
            samples = [json.loads(item) for item in self.redis.lrange(key)]
            for sample in samples:
                _restore_datetimes(sample)
            if not samples:
                continue
            samples = sorted(samples, key=lambda row: row["collected_at"] or row["ts"])
            quotes.append(samples[-1])
            features.append(orderbook_feature(samples))
            flushed_keys.append(key)
        self.write_table("quote_snapshot_1m", quotes)
        self.write_table("orderbook_feature_1m", features)
        if delete_keys and flushed_keys:
            self.redis.delete(*flushed_keys)
        return len(quotes), len(features)

    def collect_kline(self, codes: list[str], bar_type: str, adjustment: str = "raw", source: str = "tdx", limit: int | None = None) -> int:
        table = "bar_intraday" if bar_type in INTRADAY_TYPES else "bar_eod"
        total = 0
        for code in codes:
            if source == "ths" or adjustment == "qfq":
                result = self.tdx.kline_all_ths(code, bar_type, limit)
                endpoint = "/api/kline-all/ths"
                row_source = "ths"
            elif infer_asset_type(code) == "index":
                result = self.tdx.index_all(code, bar_type, limit)
                endpoint = "/api/index/all"
                row_source = self.settings.source
            else:
                result = self.tdx.kline_all_tdx(code, bar_type, limit)
                endpoint = "/api/kline-all/tdx"
                row_source = self.settings.source
            items = extract_list(result.data)
            rows = [
                normalize_bar(item, code, infer_asset_type(code), bar_type, adjustment, row_source, self.settings.price_scale)
                for item in items
                if isinstance(item, dict)
            ]
            rows.sort(key=lambda row: row["ts"])
            self.write_table(table, rows)
            status = "success" if rows else "empty"
            self.log_ingestion(endpoint, f"code={code},type={bar_type},adjustment={adjustment}", status, result.latency_ms, len(rows))
            if rows:
                self.checkpoint(endpoint, code, infer_asset_type(code), "bar", bar_type, adjustment, rows[-1]["ts"], yyyymmdd(rows[-1]["ts"]), "success")
            total += len(rows)
        return total

    def collect_minute(self, codes: list[str], trade_date: str) -> int:
        total = 0
        for code in codes:
            result = self.tdx.minute(code, trade_date)
            payload = unwrap_payload(result.data)
            actual_date = None
            if isinstance(payload, dict):
                actual_date = payload.get("date") or payload.get("Date") or payload.get("actual_date")
            items = extract_list(payload)
            rows = [
                normalize_minute(item, code, trade_date, actual_date, self.settings.source, self.settings.price_scale)
                for item in items
                if isinstance(item, dict)
            ]
            rows.sort(key=lambda row: row["ts"] or datetime.min)
            self.write_table("minute_trend", rows)
            status = "fallback_detected" if actual_date and yyyymmdd(actual_date) != trade_date else ("success" if rows else "empty")
            self.log_ingestion("/api/minute", f"code={code},date={trade_date}", status, result.latency_ms, len(rows))
            total += len(rows)
        return total

    def collect_trades(self, codes: list[str], trade_date: str) -> int:
        total = 0
        for code in codes:
            result = self.tdx.minute_trade_all(code, trade_date)
            items = extract_list(result.data)
            rows = [
                normalize_trade(item, code, trade_date, self.settings.source, self.settings.price_scale)
                for item in items
                if isinstance(item, dict)
            ]
            rows = [row for row in rows if row["ts"] is not None]
            rows.sort(key=lambda row: row["ts"])
            self.sql.delete_trade_day(code, trade_date, self.settings.source)
            self.write_table("trade_print", rows)
            self.log_ingestion("/api/minute-trade-all", f"code={code},date={trade_date}", "success" if rows else "empty", result.latency_ms, len(rows))
            total += len(rows)
        return total

    def write_table(self, table: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        written = self.ilp.write_rows(table, rows, TIMESTAMP_COLUMNS[table], SYMBOL_COLUMNS[table])
        logger.info("questdb_ilp_written", extra={"table": table, "rows": written})
        return written

    def log_ingestion(self, endpoint: str, request_key: str, status: str, latency_ms: int, row_count: int, error: str = "") -> None:
        row = {
            "ts": now_cn(),
            "source": self.settings.source,
            "endpoint": endpoint,
            "request_key": request_key,
            "status": status,
            "latency_ms": latency_ms,
            "row_count": row_count,
            "error_message": error,
        }
        try:
            self.write_table("api_ingestion_log", [row])
        except Exception:
            logger.exception("write_ingestion_log_failed", extra={"endpoint": endpoint, "status": status})

    def checkpoint(
        self,
        endpoint: str,
        code: str,
        asset_type: str,
        data_type: str,
        bar_type: str,
        adjustment: str,
        last_success_ts: datetime,
        last_success_trade_date: str,
        status: str,
    ) -> None:
        row = {
            "ts": now_cn(),
            "source": self.settings.source,
            "endpoint": endpoint,
            "code": code,
            "asset_type": asset_type,
            "data_type": data_type,
            "bar_type": bar_type,
            "adjustment": adjustment,
            "last_success_ts": last_success_ts,
            "last_success_trade_date": last_success_trade_date,
            "status": status,
        }
        self.write_table("ingestion_checkpoint", [row])

    def redis_key(self, code: str, minute: str) -> str:
        return f"{self.settings.redis_key_prefix}:{self.settings.source}:{code}:{minute}"


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Cannot JSON encode {value!r}")


def _restore_datetimes(row: dict[str, Any]) -> None:
    for key in ("ts", "collected_at", "server_ts"):
        if row.get(key):
            row[key] = parse_datetime(row[key])
