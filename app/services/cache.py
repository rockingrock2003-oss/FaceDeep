import json
import logging
from typing import Any

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger("facedeep.redis")


class RedisCache:
    def __init__(self):
        self._client: redis.Redis | None = None

    async def connect(self):
        try:
            self._client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._client.ping()
            logger.info("Redis connected")
        except Exception as e:
            logger.warning(f"Redis unavailable, caching disabled: {e}")
            self._client = None

    async def disconnect(self):
        if self._client:
            await self._client.close()
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    async def get(self, key: str) -> Any | None:
        if not self.available:
            return None
        try:
            val = await self._client.get(key)
            if val is None:
                return None
            return json.loads(val)
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None):
        if not self.available:
            return
        try:
            ttl = ttl or settings.REDIS_CACHE_TTL
            await self._client.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception:
            pass

    async def delete(self, key: str):
        if not self.available:
            return
        try:
            await self._client.delete(key)
        except Exception:
            pass

    async def delete_pattern(self, pattern: str):
        if not self.available:
            return
        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self._client.delete(*keys)
        except Exception:
            pass

    async def incr(self, key: str, ttl: int | None = None) -> int:
        if not self.available:
            return 0
        try:
            val = await self._client.incr(key)
            if val == 1 and ttl:
                await self._client.expire(key, ttl)
            return val
        except Exception:
            return 0

    async def get_counter(self, key: str) -> int:
        if not self.available:
            return 0
        try:
            val = await self._client.get(key)
            return int(val) if val else 0
        except Exception:
            return 0


cache = RedisCache()
