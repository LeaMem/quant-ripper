from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _read_env_file(path: Path) -> dict[str, str]:
    """读取简单 KEY=VALUE 配置文件；不依赖 python-dotenv，便于轻量部署。"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _merged_env(env_file: str | None = None) -> dict[str, str]:
    """按示例配置、指定 env 文件、进程环境变量的优先级合并运行配置。"""
    defaults = _read_env_file(PROJECT_ROOT / "config" / "example.env")
    selected = PROJECT_ROOT / ".env"
    if env_file:
        selected = Path(env_file)
    file_values = _read_env_file(selected)
    merged = defaults | file_values | dict(os.environ)
    return {k: v for k, v in merged.items() if v is not None}


def _get_int(env: dict[str, str], key: str, default: int) -> int:
    """读取整数配置；缺失或空字符串时使用默认值。"""
    value = env.get(key)
    return int(value) if value not in (None, "") else default


def _get_float(env: dict[str, str], key: str, default: float) -> float:
    """读取浮点数配置；缺失或空字符串时使用默认值。"""
    value = env.get(key)
    return float(value) if value not in (None, "") else default


def _get_bool(env: dict[str, str], key: str, default: bool) -> bool:
    """读取布尔配置；支持 1/true/yes/y/on 等常见真值写法。"""
    value = env.get(key)
    if value in (None, ""):
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    """项目运行配置，集中描述 TDX、Redis、QuestDB、HTTP 重试和业务单位口径。"""

    tdx_api_base_url: str
    redis_host: str
    redis_port: int
    redis_db: int
    redis_key_prefix: str
    redis_password: str | None
    quote_redis_ttl_seconds: int
    questdb_http_url: str
    questdb_pg_host: str
    questdb_pg_port: int
    questdb_pg_database: str
    questdb_pg_user: str
    questdb_pg_password: str
    questdb_ilp_host: str
    questdb_ilp_port: int
    questdb_ilp_protocol: str
    questdb_ilp_conf: str | None
    questdb_health_url: str
    http_timeout_seconds: float
    http_retries: int
    http_backoff_seconds: float
    price_scale: int
    source: str
    pgwire_required: bool

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "Settings":
        """从 `config/example.env`、`.env` 和进程环境构建不可变运行配置。"""
        env = _merged_env(env_file)
        return cls(
            tdx_api_base_url=env.get("TDX_API_BASE_URL", "http://192.168.31.236:9999").rstrip("/"),
            redis_host=env.get("REDIS_HOST", "192.168.31.99"),
            redis_port=_get_int(env, "REDIS_PORT", 6379),
            redis_db=_get_int(env, "REDIS_DB", 9),
            redis_key_prefix=env.get("REDIS_KEY_PREFIX", "quote"),
            redis_password=env.get("REDIS_PASSWORD") or None,
            quote_redis_ttl_seconds=_get_int(env, "QUOTE_REDIS_TTL_SECONDS", 172800),
            questdb_http_url=env.get("QUESTDB_HTTP_URL", "http://localhost:9005").rstrip("/"),
            questdb_pg_host=env.get("QUESTDB_PG_HOST", "localhost"),
            questdb_pg_port=_get_int(env, "QUESTDB_PG_PORT", 8812),
            questdb_pg_database=env.get("QUESTDB_PG_DATABASE", "qdb"),
            questdb_pg_user=env.get("QUESTDB_PG_USER", "admin"),
            questdb_pg_password=env.get("QUESTDB_PG_PASSWORD", "quest"),
            questdb_ilp_host=env.get("QUESTDB_ILP_HOST", "localhost"),
            questdb_ilp_port=_get_int(env, "QUESTDB_ILP_PORT", 9009),
            questdb_ilp_protocol=env.get("QUESTDB_ILP_PROTOCOL", "tcp"),
            questdb_ilp_conf=env.get("QUESTDB_ILP_CONF") or None,
            questdb_health_url=env.get("QUESTDB_HEALTH_URL", "http://localhost:9003").rstrip("/"),
            http_timeout_seconds=_get_float(env, "HTTP_TIMEOUT_SECONDS", 10.0),
            http_retries=_get_int(env, "HTTP_RETRIES", 3),
            http_backoff_seconds=_get_float(env, "HTTP_BACKOFF_SECONDS", 0.5),
            price_scale=_get_int(env, "PRICE_SCALE", 1000),
            source=env.get("DATA_SOURCE", "tdx"),
            pgwire_required=_get_bool(env, "QUESTDB_PGWIRE_REQUIRED", False),
        )
