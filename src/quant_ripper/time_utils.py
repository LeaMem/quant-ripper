from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


try:
    CN_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    CN_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def now_cn() -> datetime:
    return datetime.now(CN_TZ)


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CN_TZ)
    return dt.astimezone(timezone.utc)


def timestamp_ns(dt: datetime) -> int:
    utc = as_utc(dt)
    return int(utc.timestamp() * 1_000_000_000)


def timestamp_us(dt: datetime) -> int:
    utc = as_utc(dt)
    return int(utc.timestamp() * 1_000_000)


def parse_date_yyyymmdd(value: str | date | datetime | None = None) -> date:
    if value is None:
        return now_cn().date()
    if isinstance(value, datetime):
        return value.astimezone(CN_TZ).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    return datetime.fromisoformat(text).date()


def yyyymmdd(value: str | date | datetime | None = None) -> str:
    return parse_date_yyyymmdd(value).strftime("%Y%m%d")


def parse_datetime(value: object, trade_date: str | date | None = None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=CN_TZ)
    if isinstance(value, date):
        return datetime.combine(value, time.min, CN_TZ)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=CN_TZ)
    except ValueError:
        pass
    if len(text) == 8 and text.isdigit():
        return datetime.combine(parse_date_yyyymmdd(text), time.min, CN_TZ)
    if len(text) in (4, 5) and ":" in text:
        day = parse_date_yyyymmdd(trade_date)
        hour, minute = text.split(":", 1)
        return datetime.combine(day, time(int(hour), int(minute[:2])), CN_TZ)
    if len(text) == 6 and text.isdigit():
        day = parse_date_yyyymmdd(trade_date)
        return datetime.combine(day, time(int(text[:2]), int(text[2:4]), int(text[4:6])), CN_TZ)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=CN_TZ)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime value: {value!r}")


def minute_bucket(dt: datetime) -> datetime:
    local = dt.astimezone(CN_TZ) if dt.tzinfo else dt.replace(tzinfo=CN_TZ)
    return local.replace(second=0, microsecond=0)


def minute_key(dt: datetime) -> str:
    return minute_bucket(dt).strftime("%Y%m%d%H%M")
