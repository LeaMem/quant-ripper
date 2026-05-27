from __future__ import annotations

import _path  # noqa: F401
from datetime import datetime, timedelta, timezone
import unittest

from quant_ripper.infrastructure.questdb_ilp import QuestDbIlpWriter, build_ilp_conf


class IlpTests(unittest.TestCase):
    def test_prepare_row_splits_symbols_columns_and_timestamp(self):
        writer = QuestDbIlpWriter("tcp::addr=localhost:9009;protocol_version=2;")
        ts = datetime(2026, 5, 26, 9, 31, tzinfo=timezone(timedelta(hours=8)))

        symbols, columns, at = writer.prepare_row(
            {
                "ts": ts,
                "code": "000001",
                "source": "tdx",
                "last_price": 12340,
                "rate": 1.25,
                "collected_at": ts,
                "name": "Ping An",
            },
            "ts",
            {"code", "source"},
        )

        self.assertEqual(symbols, {"code": "000001", "source": "tdx"})
        self.assertEqual(columns["last_price"], 12340)
        self.assertEqual(columns["rate"], 1.25)
        self.assertEqual(columns["collected_at"], ts)
        self.assertEqual(columns["name"], "Ping An")
        self.assertEqual(at, ts)

    def test_build_ilp_conf_defaults_to_tcp_protocol_v2(self):
        self.assertEqual(build_ilp_conf("tcp", "localhost", 9009), "tcp::addr=localhost:9009;protocol_version=2;")
