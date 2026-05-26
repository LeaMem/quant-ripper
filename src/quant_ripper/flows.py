from __future__ import annotations

from .config import Settings
from .services import MarketIngestionService


try:
    from prefect import flow, task
except ImportError:

    def flow(fn=None, **_kwargs):
        def decorate(func):
            return func

        return decorate(fn) if fn else decorate

    def task(fn=None, **_kwargs):
        def decorate(func):
            return func

        return decorate(fn) if fn else decorate


@task(retries=2, retry_delay_seconds=10)
def init_schema_task(env_file: str | None = None) -> int:
    return MarketIngestionService(Settings.from_env(env_file)).init_schema()


@task(retries=2, retry_delay_seconds=10)
def collect_instruments_task(env_file: str | None = None) -> int:
    return MarketIngestionService(Settings.from_env(env_file)).collect_instruments()


@task(retries=3, retry_delay_seconds=5)
def collect_quotes_task(codes: list[str], env_file: str | None = None) -> tuple[int, int]:
    return MarketIngestionService(Settings.from_env(env_file)).collect_quotes(codes)


@task(retries=2, retry_delay_seconds=10)
def collect_kline_task(
    codes: list[str],
    bar_type: str = "day",
    adjustment: str = "raw",
    source: str = "tdx",
    limit: int | None = None,
    env_file: str | None = None,
) -> int:
    return MarketIngestionService(Settings.from_env(env_file)).collect_kline(codes, bar_type, adjustment, source, limit)


@flow(name="tdx-pre-market")
def pre_market_flow(env_file: str | None = None) -> dict[str, int]:
    return {
        "schema_statements": init_schema_task(env_file),
        "instrument_rows": collect_instruments_task(env_file),
    }


@flow(name="tdx-quotes-once")
def quotes_once_flow(codes: list[str], env_file: str | None = None) -> tuple[int, int]:
    return collect_quotes_task(codes, env_file)


@flow(name="tdx-kline-backfill")
def kline_backfill_flow(
    codes: list[str],
    bar_type: str = "day",
    adjustment: str = "raw",
    source: str = "tdx",
    limit: int | None = None,
    env_file: str | None = None,
) -> int:
    return collect_kline_task(codes, bar_type, adjustment, source, limit, env_file)
