from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any

from .time_utils import CN_TZ, minute_bucket, parse_date_yyyymmdd, parse_datetime, yyyymmdd


INTRADAY_TYPES = {"minute1", "minute5", "minute15", "minute30", "hour"}


def get_any(row: dict[str, Any], *names: str, default: Any = None) -> Any:
    if not isinstance(row, dict):
        return default
    lower = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name in row:
            return row[name]
        value = lower.get(name.lower())
        if value is not None:
            return value
    return default


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def price_to_li(value: Any, scale: int = 1000) -> int | None:
    number = as_float(value)
    if number is None:
        return None
    return int(round(number * scale))


def infer_exchange(code: str, exchange: str | None = None) -> str:
    if exchange:
        return exchange.lower()
    text = str(code).lower()
    if text.startswith("sh") or text.startswith("6") or text.startswith("5"):
        return "sh"
    if text.startswith("sz") or text.startswith(("0", "1", "2", "3")):
        return "sz"
    if text.startswith("bj") or text.startswith(("4", "8")):
        return "bj"
    return "unknown"


def normalize_code(code: Any) -> str:
    text = str(code or "").strip()
    if text.lower().startswith(("sh", "sz", "bj")):
        return text[2:]
    return text


def infer_asset_type(code: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    text = str(code).lower()
    bare = normalize_code(text)
    if text.startswith(("sh000", "sz399")) or (bare.startswith("399") and len(bare) == 6):
        return "index"
    if bare.startswith(("15", "16", "50", "51", "56", "58")):
        return "etf"
    return "stock"


def normalize_instrument(raw: dict[str, Any], collected_at: datetime, source: str, asset_type: str = "stock") -> dict[str, Any]:
    code = normalize_code(get_any(raw, "code", "Code", "symbol", "Symbol"))
    exchange = infer_exchange(code, get_any(raw, "exchange", "Exchange"))
    return {
        "ts": collected_at,
        "code": code,
        "exchange": exchange,
        "asset_type": get_any(raw, "asset_type", "assetType", default=asset_type),
        "name": str(get_any(raw, "name", "Name", default="")),
        "listed_date": str(get_any(raw, "listed_date", "listedDate", "ListDate", default="")),
        "delisted_date": str(get_any(raw, "delisted_date", "delistedDate", default="")),
        "status": str(get_any(raw, "status", "Status", default="listed")),
        "last_price": price_to_li(get_any(raw, "last_price", "LastPrice", "price", "Price")),
        "source": source,
    }


def snapshot_from_instrument(row: dict[str, Any], trade_date: str) -> dict[str, Any]:
    snap = dict(row)
    snap["ts"] = parse_datetime(trade_date)
    snap["trade_date"] = trade_date
    return snap


def normalize_quote(raw: dict[str, Any], collected_at: datetime, source: str, scale: int = 1000) -> dict[str, Any]:
    code = normalize_code(get_any(raw, "code", "Code", "symbol", "Symbol"))
    trade_dt = get_any(raw, "trade_date", "TradeDate", "date", "Date")
    ts = parse_datetime(get_any(raw, "time", "Time", "ts", "Timestamp"), trade_dt) or minute_bucket(collected_at)
    trade_date = yyyymmdd(trade_dt or ts)
    row = {
        "ts": minute_bucket(ts),
        "trade_date": trade_date,
        "collected_at": collected_at,
        "server_ts": parse_datetime(get_any(raw, "server_ts", "ServerTime", "time", "Time"), trade_date),
        "code": code,
        "exchange": infer_exchange(code, get_any(raw, "exchange", "Exchange")),
        "asset_type": infer_asset_type(code, get_any(raw, "asset_type", "AssetType")),
        "prev_close": price_to_li(get_any(raw, "prev_close", "PreClose", "LastClose", "YesterdayClose"), scale),
        "open_price": price_to_li(get_any(raw, "open", "Open", "open_price", "OpenPrice"), scale),
        "high_price": price_to_li(get_any(raw, "high", "High", "high_price", "HighPrice"), scale),
        "low_price": price_to_li(get_any(raw, "low", "Low", "low_price", "LowPrice"), scale),
        "last_price": price_to_li(get_any(raw, "price", "Price", "last_price", "LastPrice"), scale),
        "total_volume": as_int(get_any(raw, "volume", "Volume", "total_volume", "TotalVolume")),
        "current_volume": as_int(get_any(raw, "current_volume", "CurrentVolume", "vol", "Vol")),
        "amount": price_to_li(get_any(raw, "amount", "Amount", "total_amount", "TotalAmount"), scale),
        "inside_volume": as_int(get_any(raw, "inside_volume", "InsideVolume", "InnerVol")),
        "outside_volume": as_int(get_any(raw, "outside_volume", "OutsideVolume", "OuterVol")),
        "rate": as_float(get_any(raw, "rate", "Rate")),
        "source": source,
    }
    bid_levels = get_any(raw, "BuyLevel", "buy_level", "bid", "bids", default=[])
    ask_levels = get_any(raw, "SellLevel", "sell_level", "ask", "asks", default=[])
    for level in range(1, 6):
        bid = _level_at(bid_levels, level)
        ask = _level_at(ask_levels, level)
        row[f"bid{level}_price"] = price_to_li(get_any(raw, f"bid{level}_price", f"Bid{level}Price", default=_level_price(bid)), scale)
        row[f"bid{level}_qty"] = as_int(get_any(raw, f"bid{level}_qty", f"Bid{level}Volume", f"Bid{level}Qty", default=_level_qty(bid)))
        row[f"ask{level}_price"] = price_to_li(get_any(raw, f"ask{level}_price", f"Ask{level}Price", default=_level_price(ask)), scale)
        row[f"ask{level}_qty"] = as_int(get_any(raw, f"ask{level}_qty", f"Ask{level}Volume", f"Ask{level}Qty", default=_level_qty(ask)))
    return row


def _level_at(levels: Any, level: int) -> Any:
    if isinstance(levels, list) and len(levels) >= level:
        return levels[level - 1]
    if isinstance(levels, dict):
        return levels.get(str(level)) or levels.get(level)
    return None


def _level_price(level: Any) -> Any:
    if isinstance(level, dict):
        return get_any(level, "price", "Price")
    if isinstance(level, (list, tuple)) and level:
        return level[0]
    return None


def _level_qty(level: Any) -> Any:
    if isinstance(level, dict):
        return get_any(level, "volume", "Volume", "qty", "Qty", "number", "Number")
    if isinstance(level, (list, tuple)) and len(level) > 1:
        return level[1]
    return None


def normalize_bar(
    raw: dict[str, Any],
    code: str,
    asset_type: str,
    bar_type: str,
    adjustment: str,
    source: str,
    scale: int = 1000,
) -> dict[str, Any]:
    ts = parse_datetime(get_any(raw, "Time", "time", "date", "Date"))
    if ts is None:
        raise ValueError(f"bar row has no timestamp: {raw}")
    row = {
        "ts": ts,
        "code": normalize_code(code),
        "asset_type": asset_type,
        "bar_type": bar_type,
        "adjustment": adjustment,
        "open_price": price_to_li(get_any(raw, "Open", "open"), scale),
        "high_price": price_to_li(get_any(raw, "High", "high"), scale),
        "low_price": price_to_li(get_any(raw, "Low", "low"), scale),
        "close_price": price_to_li(get_any(raw, "Close", "close"), scale),
        "prev_close": price_to_li(get_any(raw, "PrevClose", "prev_close"), scale),
        "volume": as_int(get_any(raw, "Volume", "volume")),
        "amount": price_to_li(get_any(raw, "Amount", "amount"), scale),
        "source": source,
    }
    if bar_type in INTRADAY_TYPES:
        row["trade_date"] = yyyymmdd(ts)
    else:
        row["up_count"] = as_int(get_any(raw, "UpCount", "up_count"))
        row["down_count"] = as_int(get_any(raw, "DownCount", "down_count"))
    return row


def normalize_minute(raw: dict[str, Any], code: str, requested_date: str, actual_date: str | None, source: str, scale: int) -> dict[str, Any]:
    actual = actual_date or requested_date
    ts = parse_datetime(get_any(raw, "Time", "time"), actual)
    return {
        "ts": ts,
        "trade_date": requested_date,
        "actual_date": yyyymmdd(actual),
        "code": normalize_code(code),
        "asset_type": infer_asset_type(code),
        "price": price_to_li(get_any(raw, "Price", "price"), scale),
        "volume": as_int(get_any(raw, "Number", "number", "Volume", "volume")),
        "source": source,
    }


def normalize_trade(raw: dict[str, Any], code: str, trade_date: str, source: str, scale: int) -> dict[str, Any]:
    return {
        "ts": parse_datetime(get_any(raw, "Time", "time"), trade_date),
        "trade_date": trade_date,
        "code": normalize_code(code),
        "asset_type": infer_asset_type(code),
        "price": price_to_li(get_any(raw, "Price", "price"), scale),
        "volume": as_int(get_any(raw, "Volume", "volume")),
        "side": trade_side(get_any(raw, "Status", "status", "Side", "side")),
        "trade_count": as_int(get_any(raw, "Number", "number", "Count", "count")),
        "source": source,
    }


def trade_side(value: Any) -> int:
    text = str(value or "").strip().lower()
    if text in {"0", "b", "buy", "active_buy", "买盘", "买入"}:
        return 0
    if text in {"1", "s", "sell", "active_sell", "卖盘", "卖出"}:
        return 1
    return 2


def orderbook_feature(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ValueError("samples is empty")
    ordered = sorted(samples, key=lambda row: row["collected_at"] or row["ts"])
    first = ordered[0]
    last = ordered[-1]
    spreads = [spread(row) for row in ordered]
    spreads = [value for value in spreads if value is not None]
    imbalances = [depth_imbalance(row) for row in ordered]
    imbalances = [value for value in imbalances if value is not None]
    bid_depth = sum((last.get(f"bid{i}_qty") or 0) for i in range(1, 6))
    ask_depth = sum((last.get(f"ask{i}_qty") or 0) for i in range(1, 6))
    inside = last.get("inside_volume") or 0
    outside = last.get("outside_volume") or 0
    total_side = inside + outside
    return {
        "ts": last["ts"],
        "trade_date": last["trade_date"],
        "code": last["code"],
        "asset_type": last["asset_type"],
        "first_last_price": first.get("last_price"),
        "last_last_price": last.get("last_price"),
        "last_price": last.get("last_price"),
        "spread": spread(last),
        "avg_spread": statistics.fmean(spreads) if spreads else None,
        "max_spread": max(spreads) if spreads else None,
        "mid_price": mid_price(last),
        "bid_depth_5": bid_depth,
        "ask_depth_5": ask_depth,
        "depth_imbalance": depth_imbalance(last),
        "avg_depth_imbalance": statistics.fmean(imbalances) if imbalances else None,
        "max_depth_imbalance": max(imbalances) if imbalances else None,
        "last_depth_imbalance": depth_imbalance(last),
        "active_buy_ratio": outside / total_side if total_side else None,
        "order_pressure": (outside - inside) / total_side if total_side else None,
        "sample_count": len(samples),
        "quote_count": sum(1 for row in samples if row.get("last_price") is not None),
        "source": last["source"],
    }


def spread(row: dict[str, Any]) -> int | None:
    bid = row.get("bid1_price")
    ask = row.get("ask1_price")
    if bid is None or ask is None:
        return None
    return ask - bid


def mid_price(row: dict[str, Any]) -> int | None:
    bid = row.get("bid1_price")
    ask = row.get("ask1_price")
    if bid is None or ask is None:
        return None
    return int(round((ask + bid) / 2))


def depth_imbalance(row: dict[str, Any]) -> float | None:
    bid_depth = sum((row.get(f"bid{i}_qty") or 0) for i in range(1, 6))
    ask_depth = sum((row.get(f"ask{i}_qty") or 0) for i in range(1, 6))
    total = bid_depth + ask_depth
    if total == 0:
        return None
    return (bid_depth - ask_depth) / total


def day_start(trade_date: str) -> datetime:
    return datetime.combine(parse_date_yyyymmdd(trade_date), datetime.min.time(), CN_TZ)
