from __future__ import annotations

import _path  # noqa: F401
import unittest
from datetime import datetime, timedelta, timezone

from quant_ripper.transform import normalize_quote, orderbook_feature


class TransformTests(unittest.TestCase):
    def test_normalize_quote_and_orderbook_feature(self):
        collected_at = datetime(2026, 5, 26, 9, 31, 20, tzinfo=timezone(timedelta(hours=8)))
        raw = {
            "Code": "000001",
            "Time": "2026-05-26T09:31:20+08:00",
            "Price": 12.34,
            "Open": 12.0,
            "High": 12.5,
            "Low": 11.9,
            "Volume": 1000,
            "Amount": 12340,
            "InsideVolume": 30,
            "OutsideVolume": 70,
            "BuyLevel": [{"Price": 12.33, "Volume": 500}, {"Price": 12.32, "Volume": 400}],
            "SellLevel": [{"Price": 12.35, "Volume": 300}, {"Price": 12.36, "Volume": 200}],
        }

        row = normalize_quote(raw, collected_at, "tdx")
        self.assertEqual(row["code"], "000001")
        self.assertEqual(row["trade_date"], "20260526")
        self.assertEqual(row["last_price"], 12340)
        self.assertEqual(row["bid1_price"], 12330)
        self.assertEqual(row["ask1_price"], 12350)

        feature = orderbook_feature([row])
        self.assertEqual(feature["spread"], 20)
        self.assertEqual(feature["mid_price"], 12340)
        self.assertEqual(feature["active_buy_ratio"], 0.7)
        self.assertEqual(feature["sample_count"], 1)
        self.assertEqual(feature["quote_count"], 1)
