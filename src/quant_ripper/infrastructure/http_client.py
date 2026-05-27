from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx


logger = logging.getLogger(__name__)


@dataclass
class HttpResult:
    """HTTP JSON 响应及采集日志需要的状态码、耗时等运行元数据。"""

    data: Any
    latency_ms: int
    status_code: int


class HttpClientError(RuntimeError):
    """HTTP 请求失败、响应非成功状态或 JSON 解码失败时抛出。"""

    pass


class HttpJsonClient:
    """基于 httpx 的同步 JSON 客户端，内置超时、重试和耗时统计。"""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        retries: int = 3,
        backoff: float = 0.5,
        client: httpx.Client | None = None,
    ):
        """创建面向单个 base URL 的可复用 httpx 客户端。"""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._owns_client = client is None
        self.client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def __enter__(self) -> "HttpJsonClient":
        """支持 with 语法，返回当前客户端实例。"""
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """退出 with 语法时关闭本类创建的底层连接池。"""
        self.close()

    def close(self) -> None:
        """关闭底层 httpx 客户端；外部注入的 client 不由本类释放。"""
        if self._owns_client:
            self.client.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> HttpResult:
        """发起 GET 请求，并过滤值为 None 的查询参数。"""
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        return self._request("GET", path, params=clean_params or None)

    def post_json(self, path: str, payload: dict[str, Any] | list[Any] | None = None) -> HttpResult:
        """发起 JSON body 的 POST 请求；payload 为空时发送空对象。"""
        return self._request("POST", path, json_payload=payload or {})

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | list[Any] | None = None,
    ) -> HttpResult:
        """执行一次请求；对 429、5xx、超时和传输异常做有限重试。"""
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            started = time.perf_counter()
            try:
                response = self.client.request(method, path, params=params, json=json_payload)
                latency_ms = int((time.perf_counter() - started) * 1000)
                if self._should_retry(response.status_code):
                    # 429/5xx 多为限流或临时服务异常，保留最后错误后进入指数退避重试。
                    last_error = httpx.HTTPStatusError(
                        f"Retryable status code {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                else:
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        raise HttpClientError(f"{method} {response.request.url} failed: {exc}") from exc
                    return HttpResult(_decode_json(response), latency_ms, response.status_code)
            except (httpx.TimeoutException, httpx.TransportError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt <= self.retries:
                sleep_s = self.backoff * (2 ** (attempt - 1))
                logger.warning("http_retry", extra={"url": str(self.client.base_url.join(path)), "attempt": attempt, "sleep_s": sleep_s})
                time.sleep(sleep_s)
        raise HttpClientError(f"{method} {self.client.base_url.join(path)} failed: {last_error}") from last_error

    @staticmethod
    def _should_retry(status_code: int) -> bool:
        """判断 HTTP 状态码是否属于可重试的临时失败。"""
        return status_code == 429 or status_code >= 500


def _decode_json(response: httpx.Response) -> Any:
    """解码 JSON 响应；204 或空响应统一返回空 dict，便于上层处理。"""
    if not response.content:
        return {}
    return response.json()
