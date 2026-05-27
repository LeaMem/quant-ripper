from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from ..common.time_utils import parse_datetime
from ..core.config import Settings


class QuestDbIlpWriter:
    """使用 QuestDB 官方 Python client 写入 ILP 行情数据。"""

    def __init__(self, conf: str):
        """保存 `questdb.ingress.Sender.from_conf` 可直接使用的连接配置。"""
        self.conf = conf

    @classmethod
    def from_settings(cls, settings: Settings) -> "QuestDbIlpWriter":
        """从项目配置创建 ILP writer；显式 `QUESTDB_ILP_CONF` 优先级最高。"""
        return cls(settings.questdb_ilp_conf or build_ilp_conf(settings.questdb_ilp_protocol, settings.questdb_ilp_host, settings.questdb_ilp_port))

    def write_rows(
        self,
        table: str,
        rows: Iterable[dict[str, Any]],
        timestamp_col: str,
        symbol_cols: set[str],
    ) -> int:
        """批量写入 QuestDB；每批建立 Sender、逐行 row、最后 flush 一次。"""
        prepared = [self.prepare_row(row, timestamp_col, symbol_cols) for row in rows]
        if not prepared:
            return 0

        from questdb.ingress import Sender

        with Sender.from_conf(self.conf) as sender:
            for symbols, columns, at in prepared:
                # QuestDB ILP 中 symbol/tag 和普通字段必须分开传给官方 client。
                sender.row(table, symbols=symbols or None, columns=columns, at=at)
            sender.flush()
        return len(prepared)

    def prepare_row(
        self,
        row: dict[str, Any],
        timestamp_col: str,
        symbol_cols: set[str],
    ) -> tuple[dict[str, str], dict[str, Any], datetime]:
        """把标准化业务行拆成 QuestDB symbols、columns 和 designated timestamp。"""
        ts = parse_datetime(row.get(timestamp_col))
        if ts is None:
            raise ValueError(f"Missing designated timestamp {timestamp_col}")

        symbols: dict[str, str] = {}
        columns: dict[str, Any] = {}
        for key, value in row.items():
            if key == timestamp_col or value is None:
                continue
            if key in symbol_cols:
                # symbol 字段用于 QuestDB 索引和去重键，统一转字符串。
                symbols[key] = str(value)
            else:
                columns[key] = value
        if not columns:
            columns["_present"] = True
        return symbols, columns, ts


def build_ilp_conf(protocol: str, host: str, port: int) -> str:
    """生成 QuestDB 官方 client 配置串；默认生产链路使用 TCP ILP。"""
    normalized = protocol.strip().lower()
    if normalized == "tcp":
        return f"tcp::addr={host}:{port};protocol_version=2;"
    if normalized == "http":
        return f"http::addr={host}:{port};"
    raise ValueError(f"Unsupported QuestDB ILP protocol: {protocol}")

