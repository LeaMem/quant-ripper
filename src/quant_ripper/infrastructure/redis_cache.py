from __future__ import annotations

import redis


class RedisQuoteCache:
    """自选池盘口分钟窗口缓存，底层统一使用 redis-py 连接 Redis。"""

    def __init__(self, host: str, port: int, db: int, password: str | None = None, timeout: float = 10.0):
        """创建 Redis 客户端；响应统一解码为字符串，便于 JSON 样本读写。"""
        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            decode_responses=True,
        )

    def ping(self) -> bool:
        """用 PING 检查 Redis 连通性，供 health 命令和部署验收使用。"""
        return bool(self.client.ping())

    def rpush(self, key: str, value: str) -> int:
        """把一条标准化后的盘口 JSON 追加到分钟窗口 list。"""
        return int(self.client.rpush(key, value))

    def expire(self, key: str, seconds: int) -> bool:
        """为分钟窗口设置 TTL，避免盘中临时样本长期占用 Redis。"""
        return bool(self.client.expire(key, seconds))

    def lrange(self, key: str, start: int = 0, stop: int = -1) -> list[str]:
        """读取一个分钟窗口中的盘口样本，返回序列化 JSON 字符串列表。"""
        return [str(value) for value in self.client.lrange(key, start, stop)]

    def delete(self, *keys: str) -> int:
        """QuestDB 聚合写入成功后删除一个或多个分钟窗口 key。"""
        if not keys:
            return 0
        return int(self.client.delete(*keys))

    def scan_match(self, pattern: str, count: int = 1000) -> list[str]:
        """按模式增量扫描分钟窗口 key，避免使用阻塞式 KEYS。"""
        return [str(key) for key in self.client.scan_iter(match=pattern, count=count)]

    def raw_client(self) -> redis.Redis:
        """暴露底层 redis-py 客户端，供诊断或后续扩展命令使用。"""
        return self.client
