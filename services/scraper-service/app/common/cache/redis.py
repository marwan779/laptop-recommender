"""Redis Cache Provider Implementation.

Asynchronous Redis cache backend built on redis.asyncio with connection pooling
and fail-open resilience (never crashes user requests if Redis is unreachable).
"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.common.cache.provider import ICacheProvider
from app.common.logger import get_logger
from app.core.cache_config import get_cache_settings

logger = get_logger("scraper.common.cache.redis")


class RedisCacheProvider(ICacheProvider):
    """Production Redis cache provider with connection pooling and fail-open behavior."""

    def __init__(
        self,
        redis_url: str | None = None,
        default_ttl_seconds: int | None = None,
        client: Redis | None = None,
    ) -> None:
        settings = get_cache_settings()
        self.redis_url = redis_url or settings.redis_url
        self.default_ttl_seconds = (
            default_ttl_seconds if default_ttl_seconds is not None else settings.cache_default_ttl_seconds
        )
        self._client: Redis | None = client

    async def connect(self) -> None:
        """Initialize the async Redis client and verify connectivity."""
        if self._client is None:
            self._client = Redis.from_url(
                self.redis_url,
                decode_responses=False,
                socket_connect_timeout=2.0,
                socket_timeout=2.0,
                health_check_interval=30,
            )
        try:
            await self._client.ping()
            logger.info("Connected to Redis cache at %s", self.redis_url)
        except Exception as exc:
            logger.warning(
                "Redis cache unreachable on startup (%s). Operating in fail-open bypass mode.",
                exc,
            )

    async def close(self) -> None:
        """Close the async Redis connection pool."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as exc:
                logger.warning("Error closing Redis connection: %s", exc)
            finally:
                self._client = None

    async def get(self, key: str) -> bytes | None:
        """Retrieve raw bytes from Redis; returns None on miss or connection error."""
        if self._client is None:
            return None
        try:
            data = await self._client.get(key)
            if data is None:
                return None
            return data.encode("utf-8") if isinstance(data, str) else bytes(data)
        except (RedisError, OSError) as exc:
            logger.warning("Redis GET failed for key '%s' (%s); bypassing cache.", key, exc)
            return None

    async def set(self, key: str, value: bytes | str, ttl_seconds: int | None = None) -> None:
        """Store raw bytes in Redis with TTL; logs and continues on connection error."""
        if self._client is None:
            return
        raw_bytes = value.encode("utf-8") if isinstance(value, str) else value
        effective_ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        try:
            if effective_ttl and effective_ttl > 0:
                await self._client.setex(name=key, time=effective_ttl, value=raw_bytes)
            else:
                await self._client.set(name=key, value=raw_bytes)
        except (RedisError, OSError) as exc:
            logger.warning("Redis SET failed for key '%s' (%s); continuing.", key, exc)

    async def set_nx(self, key: str, value: bytes | str, ttl_seconds: int = 86400) -> bool:
        """Atomically claim a key using SET NX EX; fail-open on Redis errors."""
        if self._client is None:
            return True

        raw_bytes = value.encode("utf-8") if isinstance(value, str) else value
        try:
            result = await self._client.set(key, raw_bytes, nx=True, ex=ttl_seconds)
            return bool(result)
        except (RedisError, OSError) as exc:
            logger.warning(
                "Redis SET NX failed for key '%s' (%s); allowing processing (fail-open).",
                key,
                exc,
            )
            return True

    async def delete(self, key: str) -> None:
        """Delete a key from Redis; logs and continues on connection error."""
        if self._client is None:
            return
        try:
            await self._client.delete(key)
        except (RedisError, OSError) as exc:
            logger.warning("Redis DELETE failed for key '%s' (%s).", key, exc)

    async def clear_prefix(self, prefix: str) -> int:
        """Evict all keys starting with prefix using non-blocking SCAN."""
        if self._client is None:
            return 0
        try:
            keys_to_delete: list[bytes | str] = []
            async for key in self._client.scan_iter(match=f"{prefix}*", count=100):
                keys_to_delete.append(key)
            if keys_to_delete:
                return int(await self._client.delete(*keys_to_delete))
            return 0
        except (RedisError, OSError) as exc:
            logger.warning("Redis CLEAR_PREFIX failed for '%s*' (%s).", prefix, exc)
            return 0

    async def health_check(self) -> bool:
        """Ping Redis and return True if responsive."""
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except Exception:
            return False
