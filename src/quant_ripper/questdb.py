from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .config import Settings
from .http_client import HttpClientError


logger = logging.getLogger(__name__)


SYMBOL_COLUMNS: dict[str, set[str]] = {
    "instrument": {"code", "exchange", "asset_type", "listed_date", "delisted_date", "status", "source"},
    "instrument_daily_snapshot": {
        "trade_date",
        "code",
        "exchange",
        "asset_type",
        "listed_date",
        "delisted_date",
        "status",
        "source",
    },
    "trading_calendar": {"date_numeric", "source"},
    "quote_snapshot_1m": {"trade_date", "code", "exchange", "asset_type", "source"},
    "orderbook_feature_1m": {"trade_date", "code", "asset_type", "source"},
    "bar_intraday": {"trade_date", "code", "asset_type", "bar_type", "adjustment", "source"},
    "bar_eod": {"code", "asset_type", "bar_type", "adjustment", "source"},
    "adjust_factor": {"code", "ex_date", "source"},
    "minute_trend": {"trade_date", "actual_date", "code", "asset_type", "source"},
    "trade_print": {"trade_date", "code", "asset_type", "source"},
    "api_ingestion_log": {"source", "endpoint", "status"},
    "ingestion_checkpoint": {
        "source",
        "endpoint",
        "code",
        "asset_type",
        "data_type",
        "bar_type",
        "adjustment",
        "last_success_trade_date",
        "status",
    },
}


TIMESTAMP_COLUMNS: dict[str, str] = {
    "instrument": "ts",
    "instrument_daily_snapshot": "ts",
    "trading_calendar": "ts",
    "quote_snapshot_1m": "ts",
    "orderbook_feature_1m": "ts",
    "bar_intraday": "ts",
    "bar_eod": "ts",
    "adjust_factor": "updated_at",
    "minute_trend": "ts",
    "trade_print": "ts",
    "api_ingestion_log": "ts",
    "ingestion_checkpoint": "ts",
}


def split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if not in_single and not in_double and ch == "-" and nxt == "-":
            while i < len(sql) and sql[i] not in "\r\n":
                current.append(sql[i])
                i += 1
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


class QuestSqlClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def execute_file(self, path: Path) -> int:
        sql = path.read_text(encoding="utf-8")
        statements = split_sql(sql)
        for statement in statements:
            self.execute(statement)
        return len(statements)

    def execute(self, sql: str) -> Any:
        try:
            import psycopg  # type: ignore
        except ImportError as exc:
            if self.settings.pgwire_required:
                raise RuntimeError("psycopg is required for PGWire. Install with: python -m pip install .[pgwire]") from exc
            logger.warning("pgwire_unavailable_using_http_exec")
            return self._execute_http(sql)
        return self._execute_pgwire(sql, psycopg)

    def _execute_pgwire(self, sql: str, psycopg: Any) -> Any:
        conninfo = (
            f"host={self.settings.questdb_pg_host} "
            f"port={self.settings.questdb_pg_port} "
            f"dbname={self.settings.questdb_pg_database} "
            f"user={self.settings.questdb_pg_user} "
            f"password={self.settings.questdb_pg_password}"
        )
        with psycopg.connect(conninfo, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                if cur.description:
                    return cur.fetchall()
        return None

    def _execute_http(self, sql: str) -> Any:
        query = urlencode({"query": sql})
        url = f"{self.settings.questdb_http_url}/exec?{query}"
        try:
            with urlopen(url, timeout=self.settings.http_timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else None
        except Exception as exc:
            raise HttpClientError(f"QuestDB HTTP exec failed: {exc}") from exc

    def delete_trade_day(self, code: str, trade_date: str, source: str = "tdx") -> None:
        self.execute(
            "DELETE FROM trade_print "
            f"WHERE source = '{_sql_literal(source)}' "
            f"AND code = '{_sql_literal(code)}' "
            f"AND trade_date = '{_sql_literal(trade_date)}'"
        )

    def delete_trade_minute(self, code: str, trade_date: str, ts_iso: str, source: str = "tdx") -> None:
        self.execute(
            "DELETE FROM trade_print "
            f"WHERE source = '{_sql_literal(source)}' "
            f"AND code = '{_sql_literal(code)}' "
            f"AND trade_date = '{_sql_literal(trade_date)}' "
            f"AND ts = '{_sql_literal(ts_iso)}'"
        )


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")
