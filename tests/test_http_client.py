from __future__ import annotations

import json
import unittest

import _path  # noqa: F401
import httpx

from quant_ripper.http_client import HttpClientError, HttpJsonClient


class HttpJsonClientTests(unittest.TestCase):
    def test_get_sends_params_and_decodes_json(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"ok": True}, request=request)

        client = _client(handler)
        result = client.get("/api/health", {"a": "1", "skip": None})

        self.assertEqual(result.data, {"ok": True})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(seen[0].url.path, "/api/health")
        self.assertEqual(seen[0].url.params["a"], "1")
        self.assertNotIn("skip", seen[0].url.params)

    def test_post_json_sends_body(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(json.loads(request.content.decode("utf-8")), {"codes": ["000001"]})
            return httpx.Response(200, json={"rows": 1}, request=request)

        result = _client(handler).post_json("/api/batch-quote", {"codes": ["000001"]})

        self.assertEqual(result.data, {"rows": 1})

    def test_empty_response_returns_empty_dict(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(204, content=b"", request=request)

        result = _client(handler).get("/api/health")

        self.assertEqual(result.data, {})
        self.assertEqual(result.status_code, 204)

    def test_retry_500_then_success(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(500, json={"error": "busy"}, request=request)
            return httpx.Response(200, json={"ok": True}, request=request)

        result = _client(handler, retries=1).get("/api/health")

        self.assertEqual(result.data, {"ok": True})
        self.assertEqual(calls, 2)

    def test_retry_429_then_success(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(429, json={"error": "limit"}, request=request)
            return httpx.Response(200, json={"ok": True}, request=request)

        result = _client(handler, retries=1).get("/api/health")

        self.assertEqual(result.data, {"ok": True})
        self.assertEqual(calls, 2)

    def test_400_does_not_retry(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(400, json={"error": "bad"}, request=request)

        with self.assertRaises(HttpClientError):
            _client(handler, retries=2).get("/api/health")

        self.assertEqual(calls, 1)

    def test_transport_error_is_wrapped_after_retries(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ConnectError("no route", request=request)

        with self.assertRaises(HttpClientError):
            _client(handler, retries=1).get("/api/health")

        self.assertEqual(calls, 2)

    def test_invalid_json_is_wrapped(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="{bad json", request=request)

        with self.assertRaises(HttpClientError):
            _client(handler, retries=0).get("/api/health")


def _client(handler, retries: int = 0) -> HttpJsonClient:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="http://tdx.local", transport=transport)
    return HttpJsonClient("http://tdx.local", retries=retries, backoff=0, client=client)
