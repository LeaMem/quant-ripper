from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


try:
    CN_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    CN_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def now_cn() -> datetime:
    """返回中国市场时区的当前时间，用作采集时间和日志时间。"""
    return datetime.now(CN_TZ)


def as_utc(dt: datetime) -> datetime:
    """将 datetime 转为 UTC；无时区值按中国市场时间解释。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CN_TZ)
    return dt.astimezone(timezone.utc)


def timestamp_ns(dt: datetime) -> int:
    """将时间转为 Unix 纳秒时间戳，供 QuestDB ILP designated timestamp 使用。"""
    utc = as_utc(dt)
    return int(utc.timestamp() * 1_000_000_000)


def timestamp_us(dt: datetime) -> int:
    """将时间转为 Unix 微秒时间戳，供需要微秒精度的字段使用。"""
    utc = as_utc(dt)
    return int(utc.timestamp() * 1_000_000)


def parse_date_yyyymmdd(value: str | date | datetime | None = None) -> date:
    """把 yyyyMMdd、ISO 日期、date/datetime 统一解析为 date。"""
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
    """把日期类值格式化为交易日常用的 yyyyMMdd 字符串。"""
    return parse_date_yyyymmdd(value).strftime("%Y%m%d")


def parse_datetime(value: object, trade_date: str | date | None = None) -> datetime | None:
    """解析 TDX 常见日期时间格式，并返回带中国市场时区的 datetime。"""
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
        # 继续尝试 TDX 常见的纯日期、HH:MM、HHMMSS 和紧凑时间格式。
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
    """将时间向下取整到中国市场时区的一分钟桶。"""
    local = dt.astimezone(CN_TZ) if dt.tzinfo else dt.replace(tzinfo=CN_TZ)
    return local.replace(second=0, microsecond=0)


def minute_key(dt: datetime) -> str:
    """将分钟桶格式化为 Redis key 使用的 yyyyMMddHHmm。"""
    return minute_bucket(dt).strftime("%Y%m%d%H%M")
