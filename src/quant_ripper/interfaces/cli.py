from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..application.ingestion_service import MarketIngestionService
from ..common.logging import configure_logging
from ..core.config import Settings


def build_parser() -> argparse.ArgumentParser:
    """构建本地运维和 Prefect worker 可共用的命令行参数解析器。"""
    parser = argparse.ArgumentParser(prog="quant-ripper", description="TDX API to QuestDB ingestion")
    parser.add_argument("--env-file", default=None, help="Path to .env file")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="command", required=True)

    init_schema = sub.add_parser("init-schema", help="Initialize QuestDB schema")
    init_schema.add_argument("--schema", default="sql/questdb_schema.sql")

    sub.add_parser("health", help="Check TDX, QuestDB and Redis connectivity")

    instruments = sub.add_parser("collect-instruments", help="Collect stock and ETF instruments")
    instruments.add_argument("--exchange", default=None)
    instruments.add_argument("--no-etf", action="store_true")

    calendar = sub.add_parser("collect-calendar", help="Collect trading calendar range")
    calendar.add_argument("--start", required=True)
    calendar.add_argument("--end", required=True)

    quotes = sub.add_parser("collect-quotes", help="Collect one batch of 1m quote snapshots")
    quotes.add_argument("--codes", required=True, help="Comma-separated codes")

    sample = sub.add_parser("sample-watchlist", help="Sample watchlist quotes into Redis minute windows")
    sample.add_argument("--codes", required=True, help="Comma-separated codes")

    flush = sub.add_parser("flush-watchlist", help="Aggregate Redis watchlist samples and write QuestDB")
    flush.add_argument("--minute", default=None, help="yyyyMMddHHmm")
    flush.add_argument("--codes", default=None, help="Comma-separated codes")
    flush.add_argument("--keep-keys", action="store_true")

    kline = sub.add_parser("collect-kline", help="Collect K-line bars")
    kline.add_argument("--codes", required=True)
    kline.add_argument("--type", default="day", dest="bar_type")
    kline.add_argument("--adjustment", default="raw", choices=["raw", "qfq", "unknown"])
    kline.add_argument("--source", default="tdx", choices=["tdx", "ths"])
    kline.add_argument("--limit", type=int, default=None)

    minute = sub.add_parser("collect-minute", help="Collect minute trend data")
    minute.add_argument("--codes", required=True)
    minute.add_argument("--date", required=True, help="yyyyMMdd")

    trades = sub.add_parser("collect-trades", help="Collect full-day minute trade prints with DELETE+INSERT")
    trades.add_argument("--codes", required=True)
    trades.add_argument("--date", required=True, help="yyyyMMdd")

    return parser


def main() -> None:
    """执行指定采集命令，并以 JSON 输出结果，方便脚本和调度系统解析。"""
    args = build_parser().parse_args()
    configure_logging(args.log_level)
    settings = Settings.from_env(args.env_file)
    service = MarketIngestionService(settings)

    if args.command == "init-schema":
        count = service.init_schema(Path(args.schema))
        print(json.dumps({"ok": True, "statements": count}, ensure_ascii=False))
    elif args.command == "health":
        print(json.dumps(service.health(), ensure_ascii=False, indent=2, default=str))
    elif args.command == "collect-instruments":
        rows = service.collect_instruments(exchange=args.exchange, include_etf=not args.no_etf)
        print(json.dumps({"ok": True, "rows": rows}, ensure_ascii=False))
    elif args.command == "collect-calendar":
        rows = service.collect_calendar(args.start, args.end)
        print(json.dumps({"ok": True, "rows": rows}, ensure_ascii=False))
    elif args.command == "collect-quotes":
        quotes, features = service.collect_quotes(_codes(args.codes))
        print(json.dumps({"ok": True, "quote_rows": quotes, "feature_rows": features}, ensure_ascii=False))
    elif args.command == "sample-watchlist":
        rows = service.sample_watchlist(_codes(args.codes))
        print(json.dumps({"ok": True, "redis_rows": rows}, ensure_ascii=False))
    elif args.command == "flush-watchlist":
        quotes, features = service.flush_watchlist(args.minute, _codes(args.codes) if args.codes else None, delete_keys=not args.keep_keys)
        print(json.dumps({"ok": True, "quote_rows": quotes, "feature_rows": features}, ensure_ascii=False))
    elif args.command == "collect-kline":
        rows = service.collect_kline(_codes(args.codes), args.bar_type, args.adjustment, args.source, args.limit)
        print(json.dumps({"ok": True, "rows": rows}, ensure_ascii=False))
    elif args.command == "collect-minute":
        rows = service.collect_minute(_codes(args.codes), args.date)
        print(json.dumps({"ok": True, "rows": rows}, ensure_ascii=False))
    elif args.command == "collect-trades":
        rows = service.collect_trades(_codes(args.codes), args.date)
        print(json.dumps({"ok": True, "rows": rows}, ensure_ascii=False))
    else:
        raise SystemExit(f"Unknown command: {args.command}")


def _codes(value: str) -> list[str]:
    """解析逗号分隔证券代码，自动去掉空白和空项。"""
    return [item.strip() for item in value.split(",") if item.strip()]
