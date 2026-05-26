from __future__ import annotations

from typing import Any

from .http_client import HttpJsonClient, HttpResult


class TdxApiError(RuntimeError):
    pass


class TdxClient:
    def __init__(self, http: HttpJsonClient):
        self.http = http

    def health(self) -> HttpResult:
        return self.http.get("/api/health")

    def server_status(self) -> HttpResult:
        return self.http.get("/api/server-status")

    def codes(self, exchange: str | None = None) -> HttpResult:
        return self.http.get("/api/codes", {"exchange": exchange})

    def etf_codes(self, limit: int | None = None, prefix: str | None = None) -> HttpResult:
        return self.http.get("/api/etf-codes", {"limit": limit, "prefix": prefix})

    def stock_codes(self, limit: int | None = None, prefix: str | None = None) -> HttpResult:
        return self.http.get("/api/stock-codes", {"limit": limit, "prefix": prefix})

    def quote(self, code: str) -> HttpResult:
        return self.http.get("/api/quote", {"code": code})

    def batch_quote(self, codes: list[str]) -> HttpResult:
        return self.http.post_json("/api/batch-quote", {"codes": codes})

    def kline_all_tdx(self, code: str, bar_type: str = "day", limit: int | None = None) -> HttpResult:
        return self.http.get("/api/kline-all/tdx", {"code": code, "type": bar_type, "limit": limit})

    def kline_all_ths(self, code: str, bar_type: str = "day", limit: int | None = None) -> HttpResult:
        return self.http.get("/api/kline-all/ths", {"code": code, "type": bar_type, "limit": limit})

    def kline_history(
        self,
        code: str,
        bar_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> HttpResult:
        return self.http.get(
            "/api/kline-history",
            {"code": code, "type": bar_type, "start_date": start_date, "end_date": end_date, "limit": limit},
        )

    def index_all(self, code: str, bar_type: str = "day", limit: int | None = None) -> HttpResult:
        return self.http.get("/api/index/all", {"code": code, "type": bar_type, "limit": limit})

    def minute(self, code: str, trade_date: str | None = None) -> HttpResult:
        return self.http.get("/api/minute", {"code": code, "date": trade_date})

    def minute_trade_all(self, code: str, trade_date: str | None = None) -> HttpResult:
        return self.http.get("/api/minute-trade-all", {"code": code, "date": trade_date})

    def workday_range(self, start: str, end: str) -> HttpResult:
        return self.http.get("/api/workday/range", {"start": start, "end": end})


def unwrap_payload(data: Any) -> Any:
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
    payload = unwrap_payload(payload)
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("list", "List", "items", "Items", "codes", "Codes", "data", "Data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return [payload]
