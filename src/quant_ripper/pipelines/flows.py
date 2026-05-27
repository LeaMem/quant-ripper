from __future__ import annotations

from ..core.config import Settings
from ..application.ingestion_service import MarketIngestionService


try:
    from prefect import flow, task
except ImportError:

    def flow(fn=None, **_kwargs):
        """Prefect 未安装时的 flow 空装饰器，允许本地 CLI 继续导入模块。"""
        def decorate(func):
            """直接返回原函数，不注册 Prefect flow。"""
            return func

        return decorate(fn) if fn else decorate

    def task(fn=None, **_kwargs):
        """Prefect 未安装时的 task 空装饰器，保持函数可直接调用。"""
        def decorate(func):
            """直接返回原函数，不注册 Prefect task。"""
            return func

        return decorate(fn) if fn else decorate


@task(retries=2, retry_delay_seconds=10)
def init_schema_task(env_file: str | None = None) -> int:
    """Prefect task：初始化 QuestDB schema，返回执行语句数量。"""
    return MarketIngestionService(Settings.from_env(env_file)).init_schema()


@task(retries=2, retry_delay_seconds=10)
def collect_instruments_task(env_file: str | None = None) -> int:
    """Prefect task：刷新股票/ETF 主数据和日快照。"""
    return MarketIngestionService(Settings.from_env(env_file)).collect_instruments()


@task(retries=3, retry_delay_seconds=5)
def collect_quotes_task(codes: list[str], env_file: str | None = None) -> tuple[int, int]:
    """Prefect task：采集一批盘口快照并写入特征表。"""
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
    """Prefect task：按代码批次采集 K 线，支持 raw/qfq/source 参数。"""
    return MarketIngestionService(Settings.from_env(env_file)).collect_kline(codes, bar_type, adjustment, source, limit)


@task(retries=3, retry_delay_seconds=5)
def sample_watchlist_task(codes: list[str], env_file: str | None = None) -> int:
    """Prefect task：把自选池高频盘口样本写入 Redis 分钟窗口。"""
    return MarketIngestionService(Settings.from_env(env_file)).sample_watchlist(codes)


@task(retries=3, retry_delay_seconds=5)
def flush_watchlist_task(minute: str | None = None, codes: list[str] | None = None, env_file: str | None = None) -> tuple[int, int]:
    """Prefect task：聚合 Redis 分钟窗口并写入 QuestDB。"""
    return MarketIngestionService(Settings.from_env(env_file)).flush_watchlist(minute, codes)


@task(retries=2, retry_delay_seconds=10)
def collect_minute_task(codes: list[str], trade_date: str, env_file: str | None = None) -> int:
    """Prefect task：采集指定交易日的分时走势。"""
    return MarketIngestionService(Settings.from_env(env_file)).collect_minute(codes, trade_date)


@task(retries=2, retry_delay_seconds=10)
def collect_trades_task(codes: list[str], trade_date: str, env_file: str | None = None) -> int:
    """Prefect task：按 DELETE + INSERT 覆盖语义刷新单日成交明细。"""
    return MarketIngestionService(Settings.from_env(env_file)).collect_trades(codes, trade_date)


@flow(name="tdx-pre-market")
def pre_market_flow(env_file: str | None = None) -> dict[str, int]:
    """盘前 flow：初始化表结构并刷新标的主数据。"""
    return {
        "schema_statements": init_schema_task(env_file),
        "instrument_rows": collect_instruments_task(env_file),
    }


@flow(name="tdx-quotes-once")
def quotes_once_flow(codes: list[str], env_file: str | None = None) -> tuple[int, int]:
    """盘口 flow：执行一次批量盘口快照和特征采集。"""
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
    """K 线补数 flow：按代码批次补历史 K 线。"""
    return collect_kline_task(codes, bar_type, adjustment, source, limit, env_file)


@flow(name="tdx-watchlist-sample")
def watchlist_sample_flow(codes: list[str], env_file: str | None = None) -> int:
    """自选池采样 flow：把一次自选池盘口样本写入 Redis。"""
    return sample_watchlist_task(codes, env_file)


@flow(name="tdx-watchlist-flush")
def watchlist_flush_flow(minute: str | None = None, codes: list[str] | None = None, env_file: str | None = None) -> tuple[int, int]:
    """自选池聚合 flow：把 Redis 样本聚合为 QuestDB 1 分钟数据。"""
    return flush_watchlist_task(minute, codes, env_file)


@flow(name="tdx-minute-backfill")
def minute_backfill_flow(codes: list[str], trade_date: str, env_file: str | None = None) -> int:
    """分时补数 flow：补指定交易日的 minute_trend 数据。"""
    return collect_minute_task(codes, trade_date, env_file)


@flow(name="tdx-trade-backfill")
def trade_backfill_flow(codes: list[str], trade_date: str, env_file: str | None = None) -> int:
    """成交补数 flow：按交易日覆盖刷新 trade_print 数据。"""
    return collect_trades_task(codes, trade_date, env_file)
