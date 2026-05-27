from __future__ import annotations

from typing import Any

from .http_client import HttpJsonClient, HttpResult


class TdxApiError(RuntimeError):
    """TDX API 返回业务失败码时抛出，避免失败响应进入事实表。"""

    pass


class TdxClient:
    """TDX HTTP API 的轻量 facade，集中维护采集链路使用的 endpoint。"""

    def __init__(self, http: HttpJsonClient):
        """注入已配置的 JSON HTTP 客户端，便于测试和统一重试策略。"""
        self.http = http

    def health(self) -> HttpResult:
        """调用轻量健康检查接口，用于 CLI/部署前连通性验证。"""
        return self.http.get("/api/health")

    def server_status(self) -> HttpResult:
        """调用详细服务状态接口，用于运维监控 TDX 服务连接状态。"""
        return self.http.get("/api/server-status")

    def codes(self, exchange: str | None = None) -> HttpResult:
        """获取股票主数据；可按交易所过滤，写入 instrument 表。"""
        return self.http.get("/api/codes", {"exchange": exchange})

    def etf_codes(self, limit: int | None = None, prefix: str | None = None) -> HttpResult:
        """获取 ETF 代码数据，用于 ETF 主数据采集和交叉校验。"""
        return self.http.get("/api/etf-codes", {"limit": limit, "prefix": prefix})

    def stock_codes(self, limit: int | None = None, prefix: str | None = None) -> HttpResult:
        """获取股票代码列表，用于和 `/api/codes` 主数据做交叉校验。"""
        return self.http.get("/api/stock-codes", {"limit": limit, "prefix": prefix})

    def quote(self, code: str) -> HttpResult:
        """获取少量标的实时盘口；主链路批量采集优先用 batch_quote。"""
        return self.http.get("/api/quote", {"code": code})

    def batch_quote(self, codes: list[str]) -> HttpResult:
        """批量获取实时盘口，是全市场 1 分钟采样和自选池采样主入口。"""
        return self.http.post_json("/api/batch-quote", {"codes": codes})

    def kline_all_tdx(self, code: str, bar_type: str = "day", limit: int | None = None) -> HttpResult:
        """获取 TDX 原始不复权 K 线，落库时使用 `source=tdx, adjustment=raw`。"""
        return self.http.get("/api/kline-all/tdx", {"code": code, "type": bar_type, "limit": limit})

    def kline_all_ths(self, code: str, bar_type: str = "day", limit: int | None = None) -> HttpResult:
        """获取 THS 前复权 K 线，落库时使用 `source=ths, adjustment=qfq`。"""
        return self.http.get("/api/kline-all/ths", {"code": code, "type": bar_type, "limit": limit})

    def kline_history(
        self,
        code: str,
        bar_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> HttpResult:
        """按时间窗口获取 K 线，用于小范围修补和缺口补数。"""
        return self.http.get(
            "/api/kline-history",
            {"code": code, "type": bar_type, "start_date": start_date, "end_date": end_date, "limit": limit},
        )

    def index_all(self, code: str, bar_type: str = "day", limit: int | None = None) -> HttpResult:
        """获取指数全量 K 线，供指数标的历史行情采集使用。"""
        return self.http.get("/api/index/all", {"code": code, "type": bar_type, "limit": limit})

    def minute(self, code: str, trade_date: str | None = None) -> HttpResult:
        """获取分时走势；返回日期可能回退，上层需记录 actual_date。"""
        return self.http.get("/api/minute", {"code": code, "date": trade_date})

    def minute_trade_all(self, code: str, trade_date: str | None = None) -> HttpResult:
        """获取单日分钟时间戳成交明细，上层按交易日桶覆盖写入。"""
        return self.http.get("/api/minute-trade-all", {"code": code, "date": trade_date})

    def workday_range(self, start: str, end: str) -> HttpResult:
        """获取指定闭区间内的交易日历，写入 trading_calendar 表。"""
        return self.http.get("/api/workday/range", {"start": start, "end": end})


def unwrap_payload(data: Any) -> Any:
    """校验 TDX 响应 envelope，并返回 data/result 等业务 payload。"""
    if not isinstance(data, dict):
        return data
    code = data.get("code", data.get("Code"))
    if code not in (None, 0, "0", "success", "ok"):
        message = data.get("message") or data.get("msg") or data.get("error") or data
        raise TdxApiError(str(message))
    for key in ("data", "Data", "result", "Result"):
        if key in data:
            return data[key]
    return data


def extract_list(payload: Any) -> list[Any]:
    """把 TDX 常见列表形态统一成 Python list，便于上层批量标准化。"""
    payload = unwrap_payload(payload)
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        # 不同 endpoint 可能把列表放在 list/List/items/codes/data 等字段里。
        for key in ("list", "List", "items", "Items", "codes", "Codes", "data", "Data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return [payload]
