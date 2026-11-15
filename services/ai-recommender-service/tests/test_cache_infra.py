"""Tests for the cache provider abstractions and fail-open Redis behaviour."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from redis.exceptions import RedisError

import app.common.cache.memory as memory_module
from app.common.cache import ICacheProvider, InMemoryCacheProvider, RedisCacheProvider
from app.core.cache_config import CacheSettings


class _FakeAsyncRedis:
    """Async Redis double covering the methods used by RedisCacheProvider."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.setex_calls: list[tuple[str, int, bytes]] = []
        self.set_calls: list[tuple[str, bytes, bool, int | None]] = []
        self.delete_calls: list[tuple[bytes | str, ...]] = []
        self.scan_calls: list[dict[str, Any]] = []
        self.scan_items: list[bytes | str] = []
        self.ping_result = True
        self.ping_error: Exception | None = None
        self.error: Exception | None = None
        self.closed = False

    def _raise_if_needed(self) -> None:
        if self.error is not None:
            raise self.error

    async def get(self, key: str) -> bytes | None:
        self._raise_if_needed()
        return self.store.get(key)

    async def setex(self, name: str, time: int, value: bytes) -> bool:
        self._raise_if_needed()
        self.setex_calls.append((name, time, value))
        self.store[name] = value
        return True

    async def set(
        self,
        name: str,
        value: bytes,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        self._raise_if_needed()
        self.set_calls.append((name, value, nx, ex))
        if nx and name in self.store:
            return None
        self.store[name] = value
        return True

    async def delete(self, *keys: bytes | str) -> int:
        self._raise_if_needed()
        self.delete_calls.append(keys)
        return len(keys)

    async def scan_iter(self, match: str, count: int):
        self._raise_if_needed()
        self.scan_calls.append({"match": match, "count": count})
        for item in self.scan_items:
            yield item

    async def ping(self) -> bool:
        if self.ping_error is not None:
            raise self.ping_error
        return self.ping_result

    async def aclose(self) -> None:
        self.closed = True


def test_in_memory_provider_round_trip_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(memory_module.time, "monotonic", lambda: now[0])

    async def scenario() -> None:
        cache = InMemoryCacheProvider(default_ttl_seconds=3600)
        assert isinstance(cache, ICacheProvider)

        await cache.set("plain", b"value")
        assert await cache.get("plain") == b"value"
        assert await cache.get("missing") is None

        await cache.set("short", "text", ttl_seconds=10)
        assert await cache.get("short") == b"text"
        now[0] = 109.9
        assert await cache.get("short") == b"text"
        now[0] = 110.0
        assert await cache.get("short") is None
        assert "short" not in cache._store

    asyncio.run(scenario())


def test_in_memory_provider_set_nx_expiry_delete_and_clear_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [1000.0]
    monkeypatch.setattr(memory_module.time, "monotonic", lambda: now[0])

    async def scenario() -> None:
        cache = InMemoryCacheProvider(default_ttl_seconds=3600)

        assert await cache.set_nx("claim", b"first", ttl_seconds=5) is True
        assert await cache.set_nx("claim", b"second", ttl_seconds=5) is False
        assert await cache.get("claim") == b"first"

        await cache.delete("claim")
        assert await cache.set_nx("claim", b"third", ttl_seconds=5) is True

        now[0] = 1005.0
        assert await cache.set_nx("claim", b"after-expiry", ttl_seconds=5) is True
        assert await cache.get("claim") == b"after-expiry"

        await cache.set("prefix:a", b"1")
        await cache.set("prefix:b", b"2")
        await cache.set("other:c", b"3")
        assert await cache.clear_prefix("prefix:") == 2
        assert await cache.get("prefix:a") is None
        assert await cache.get("prefix:b") is None
        assert await cache.get("other:c") == b"3"

    asyncio.run(scenario())


def test_in_memory_provider_close_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_module.time, "monotonic", lambda: 100.0)

    async def scenario() -> None:
        cache = InMemoryCacheProvider()
        await cache.set("key", b"value")
        await cache.close()

        assert await cache.health_check() is False
        assert await cache.get("key") is None
        assert await cache.set_nx("key", b"new") is True
        await cache.set("key", b"ignored")
        assert await cache.get("key") is None

        await cache.connect()
        assert await cache.health_check() is True

    asyncio.run(scenario())


def test_redis_provider_happy_path_and_ttl_branches() -> None:
    async def scenario() -> None:
        client = _FakeAsyncRedis()
        settings = CacheSettings(redis_scan_count=42)
        cache = RedisCacheProvider(client=client, cache_settings=settings)

        await cache.set("with-ttl", b"bytes", ttl_seconds=30)
        assert client.setex_calls == [("with-ttl", 30, b"bytes")]

        await cache.set("no-ttl-text", "text", ttl_seconds=0)
        assert client.set_calls[-1] == ("no-ttl-text", b"text", False, None)
        assert client.store["no-ttl-text"] == b"text"

        client.store["present"] = b"stored-bytes"
        assert await cache.get("present") == b"stored-bytes"
        assert await cache.get("absent") is None

        assert await cache.set_nx("present", b"new", ttl_seconds=15) is False
        assert await cache.set_nx("fresh", "value", ttl_seconds=15) is True
        assert client.set_calls[-1] == ("fresh", b"value", True, 15)

        client.scan_items = [b"inbox:a", b"inbox:b"]
        assert await cache.clear_prefix("inbox:") == 2
        assert client.scan_calls == [{"match": "inbox:*", "count": 42}]
        assert client.delete_calls == [(b"inbox:a", b"inbox:b")]

        assert await cache.health_check() is True
        client.ping_result = False
        assert await cache.health_check() is False
        client.ping_result = True
        client.ping_error = RuntimeError("ping failed")
        assert await cache.health_check() is False

    asyncio.run(scenario())


@pytest.mark.parametrize("error", [RedisError("redis down"), OSError("socket down")])
def test_redis_provider_fails_open_on_errors(error: Exception) -> None:
    async def scenario() -> None:
        client = _FakeAsyncRedis()
        client.error = error
        cache = RedisCacheProvider(client=client)

        assert await cache.get("key") is None
        await cache.set("key", b"value")
        assert await cache.set_nx("key", b"value") is True
        await cache.delete("key")
        assert await cache.clear_prefix("key:") == 0
        client.ping_error = error
        assert await cache.health_check() is False

    asyncio.run(scenario())


def test_redis_provider_fails_open_without_client() -> None:
    async def scenario() -> None:
        cache = RedisCacheProvider(client=None)

        assert await cache.get("key") is None
        await cache.set("key", b"value")
        assert await cache.set_nx("key", b"value") is True
        await cache.delete("key")
        assert await cache.clear_prefix("key:") == 0
        assert await cache.health_check() is False

    asyncio.run(scenario())


def test_cache_settings_empty_strings_use_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "   ")
    monkeypatch.setenv("CACHE_DEFAULT_TTL_SECONDS", "")
    monkeypatch.setenv("REDIS_SCAN_COUNT", "")

    settings = CacheSettings()
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.cache_default_ttl_seconds == 86400
    assert settings.redis_scan_count == 100
    assert settings.redis_socket_connect_timeout_seconds == 2.0
    assert settings.redis_socket_timeout_seconds == 2.0
    assert settings.redis_health_check_interval_seconds == 30

    explicit = CacheSettings(redis_url="", cache_default_ttl_seconds=123)
    assert explicit.redis_url == "redis://localhost:6379/0"
    assert explicit.cache_default_ttl_seconds == 123
