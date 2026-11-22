"""Кэш и счётчики: Redis в production, память — для тестов и отладки."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol

from app.core.logging import get_logger

log = get_logger(__name__)


class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl: int | None = None) -> None: ...
    async def delete(self, *keys: str) -> None: ...
    async def incr(self, key: str, ttl: int | None = None) -> int: ...
    async def close(self) -> None: ...


class MemoryCache:
    """Потокобезопасный кэш в памяти процесса (один воркер)."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}
        self._lock = asyncio.Lock()

    def _alive(self, key: str) -> tuple[str, float | None] | None:
        item = self._data.get(key)
        if item is None:
            return None
        if item[1] is not None and item[1] < time.monotonic():
            self._data.pop(key, None)
            return None
        return item

    async def get(self, key: str) -> str | None:
        item = self._alive(key)
        return item[0] if item else None

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        async with self._lock:
            expires = time.monotonic() + ttl if ttl else None
            self._data[key] = (str(value), expires)

    async def delete(self, *keys: str) -> None:
        async with self._lock:
            for key in keys:
                self._data.pop(key, None)

    async def incr(self, key: str, ttl: int | None = None) -> int:
        async with self._lock:
            current = int(self._alive(key)[0]) if self._alive(key) else 0
            value = current + 1
            expires = self._data[key][1] if key in self._data else (time.monotonic() + ttl if ttl else None)
            self._data[key] = (str(value), expires)
            return value

    async def keys(self, prefix: str) -> list[str]:
        return [key for key in list(self._data) if key.startswith(prefix)]

    async def close(self) -> None:
        self._data.clear()


class RedisCache:
    """Кэш поверх redis.asyncio."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        value = await self._client.get(key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        await self._client.set(key, value, ex=ttl)

    async def delete(self, *keys: str) -> None:
        if keys:
            await self._client.delete(*keys)

    async def incr(self, key: str, ttl: int | None = None) -> int:
        value = await self._client.incr(key)
        if value == 1 and ttl:
            await self._client.expire(key, ttl)
        return int(value)

    async def close(self) -> None:
        await self._client.aclose()


async def build_cache(redis_url: str) -> Cache:
    if not redis_url:
        log.warning("IRIS_REDIS_URL не задан: используется кэш в памяти (только для одного процесса)")
        return MemoryCache()
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(redis_url, decode_responses=False)
        await client.ping()
        log.info("Redis подключён", extra={"url": redis_url})
        return RedisCache(client)
    except Exception as exc:  # noqa: BLE001 - отказ Redis не должен убивать бота
        log.error("Redis недоступен, используется кэш в памяти", extra={"error": str(exc)})
        return MemoryCache()
