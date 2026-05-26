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
    data: Any
    latency_ms: int
    status_code: int


class HttpClientError(RuntimeError):
    pass


class HttpJsonClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        retries: int = 3,
        backoff: float = 0.5,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._owns_client = client is None
        self.client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def __enter__(self) -> "HttpJsonClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> HttpResult:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        return self._request("GET", path, params=clean_params or None)

    def post_json(self, path: str, payload: dict[str, Any] | list[Any] | None = None) -> HttpResult:
        return self._request("POST", path, json_payload=payload or {})

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | list[Any] | None = None,
    ) -> HttpResult:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            started = time.perf_counter()
            try:
                response = self.client.request(method, path, params=params, json=json_payload)
                latency_ms = int((time.perf_counter() - started) * 1000)
                if self._should_retry(response.status_code):
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
        return status_code == 429 or status_code >= 500


def _decode_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    return response.json()
