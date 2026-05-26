from __future__ import annotations

import math
import socket
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from .time_utils import parse_datetime, timestamp_ns, timestamp_us


def _escape_ident(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _escape_string(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _format_field(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value}i"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return repr(value)
    if isinstance(value, (datetime, date)):
        return f"{timestamp_us(parse_datetime(value))}t"
    return f'"{_escape_string(str(value))}"'


class QuestIlpWriter:
    def __init__(self, host: str, port: int, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def build_lines(
        self,
        table: str,
        rows: Iterable[dict[str, Any]],
        timestamp_col: str,
        symbol_cols: set[str],
    ) -> list[str]:
        lines: list[str] = []
        for row in rows:
            ts = parse_datetime(row.get(timestamp_col))
            if ts is None:
                raise ValueError(f"Missing designated timestamp {timestamp_col} for table {table}")
            tags = []
            fields = []
            for key, value in row.items():
                if key == timestamp_col or value is None:
                    continue
                if key in symbol_cols:
                    tags.append(f"{_escape_ident(key)}={_escape_ident(str(value))}")
                    continue
                rendered = _format_field(value)
                if rendered is not None:
                    fields.append(f"{_escape_ident(key)}={rendered}")
            if not fields:
                fields.append("_present=true")
            tag_part = "," + ",".join(tags) if tags else ""
            lines.append(f"{_escape_ident(table)}{tag_part} {','.join(fields)} {timestamp_ns(ts)}")
        return lines

    def write_rows(
        self,
        table: str,
        rows: Iterable[dict[str, Any]],
        timestamp_col: str,
        symbol_cols: set[str],
    ) -> int:
        lines = self.build_lines(table, rows, timestamp_col, symbol_cols)
        if not lines:
            return 0
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(payload)
        return len(lines)
