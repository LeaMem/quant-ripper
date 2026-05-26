from __future__ import annotations

import socket
from typing import Any


class RedisProtocolError(RuntimeError):
    pass


class MinimalRedis:
    def __init__(self, host: str, port: int, db: int, password: str | None = None, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.timeout = timeout

    def ping(self) -> bool:
        return self.command("PING") == "PONG"

    def rpush(self, key: str, value: str) -> int:
        return int(self.command("RPUSH", key, value))

    def expire(self, key: str, seconds: int) -> int:
        return int(self.command("EXPIRE", key, str(seconds)))

    def lrange(self, key: str, start: int = 0, stop: int = -1) -> list[str]:
        values = self.command("LRANGE", key, str(start), str(stop))
        return [v.decode("utf-8") if isinstance(v, bytes) else v for v in values]

    def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        return int(self.command("DEL", *keys))

    def scan_match(self, pattern: str, count: int = 1000) -> list[str]:
        cursor = "0"
        keys: list[str] = []
        while True:
            cursor, batch = self.command("SCAN", cursor, "MATCH", pattern, "COUNT", str(count))
            keys.extend(k.decode("utf-8") if isinstance(k, bytes) else k for k in batch)
            if str(cursor) == "0":
                break
        return keys

    def command(self, *parts: str) -> Any:
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            file = sock.makefile("rb")
            if self.password:
                sock.sendall(_encode_command("AUTH", self.password))
                _read_resp(file)
            if self.db:
                sock.sendall(_encode_command("SELECT", str(self.db)))
                _read_resp(file)
            sock.sendall(_encode_command(*parts))
            return _read_resp(file)


def _encode_command(*parts: str) -> bytes:
    encoded = [str(p).encode("utf-8") for p in parts]
    payload = f"*{len(encoded)}\r\n".encode("ascii")
    for part in encoded:
        payload += f"${len(part)}\r\n".encode("ascii") + part + b"\r\n"
    return payload


def _read_line(file: Any) -> bytes:
    line = file.readline()
    if not line:
        raise RedisProtocolError("Unexpected EOF from Redis")
    return line.rstrip(b"\r\n")


def _read_resp(file: Any) -> Any:
    prefix = file.read(1)
    if prefix == b"+":
        return _read_line(file).decode("utf-8")
    if prefix == b"-":
        raise RedisProtocolError(_read_line(file).decode("utf-8"))
    if prefix == b":":
        return int(_read_line(file))
    if prefix == b"$":
        length = int(_read_line(file))
        if length == -1:
            return None
        data = file.read(length)
        file.read(2)
        return data
    if prefix == b"*":
        length = int(_read_line(file))
        if length == -1:
            return None
        return [_read_resp(file) for _ in range(length)]
    raise RedisProtocolError(f"Unknown RESP prefix: {prefix!r}")
