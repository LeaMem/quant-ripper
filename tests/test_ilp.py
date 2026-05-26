from __future__ import annotations

import _path  # noqa: F401
import unittest
from datetime import datetime, timedelta, timezone

from quant_ripper.ilp import QuestIlpWriter


class IlpTests(unittest.TestCase):
    def test_build_lines_formats_symbols_fields_and_timestamps(self):
        writer = QuestIlpWriter("localhost", 9009)
        ts = datetime(2026, 5, 26, 9, 31, tzinfo=timezone(timedelta(hours=8)))

        lines = writer.build_lines(
            "quote_snapshot_1m",
            [
                {
                    "ts": ts,
                    "code": "000001",
                    "source": "tdx",
                    "last_price": 12340,
                    "rate": 1.25,
                    "collected_at": ts,
                    "name": "Ping An",
                }
            ],
            "ts",
            {"code", "source"},
        )

        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertTrue(line.startswith("quote_snapshot_1m,code=000001,source=tdx "))
        self.assertIn("last_price=12340i", line)
        self.assertIn("rate=1.25", line)
        self.assertIn("collected_at=", line)
        self.assertIn("t", line)
        self.assertIn('name="Ping An"', line)
        self.assertTrue(line.endswith("1779759060000000000"))
