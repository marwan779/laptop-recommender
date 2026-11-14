"""Unit tests for scraper-service cache providers and atomic set_nx claims."""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from app.common.cache import ICacheProvider, InMemoryCacheProvider, RedisCacheProvider


def test_in_memory_provider_implements_contract():
    assert issubclass(InMemoryCacheProvider, ICacheProvider)
    assert isinstance(InMemoryCacheProvider(), ICacheProvider)


@pytest.mark.anyio
async def test_in_memory_set_nx_claims_once():
    cache = InMemoryCacheProvider(default_ttl_seconds=60)
    await cache.connect()

    assert await cache.set_nx("inbox:msg-1", b"PROCESSING", ttl_seconds=30) is True
    assert await cache.get("inbox:msg-1") == b"PROCESSING"

    # Second claim for the same message id is rejected.
    assert await cache.set_nx("inbox:msg-1", b"PROCESSING", ttl_seconds=30) is False

    await cache.delete("inbox:msg-1")
    assert await cache.set_nx("inbox:msg-1", b"PROCESSING", ttl_seconds=30) is True


@pytest.mark.anyio
async def test_in_memory_set_nx_reclaims_expired_key(monkeypatch):
    current_time = 1000.0
    monkeypatch.setattr("app.common.cache.memory.time.monotonic", lambda: current_time)

    cache = InMemoryCacheProvider()
    assert await cache.set_nx("inbox:msg-2", b"PROCESSING", ttl_seconds=10) is True

    current_time = 1009.9
    assert await cache.set_nx("inbox:msg-2", b"PROCESSING", ttl_seconds=10) is False

    current_time = 1010.1
    assert await cache.set_nx("inbox:msg-2", b"PROCESSING", ttl_seconds=10) is True


@pytest.mark.anyio
async def test_redis_set_nx_uses_atomic_set():
    mock_client = AsyncMock()
    mock_client.set.return_value = True

    provider = RedisCacheProvider(client=mock_client)
    assert await provider.set_nx("inbox:msg-3", b"PROCESSING", ttl_seconds=90) is True
    mock_client.set.assert_awaited_once_with("inbox:msg-3", b"PROCESSING", nx=True, ex=90)

    mock_client.set.return_value = None
    assert await provider.set_nx("inbox:msg-3", b"PROCESSING", ttl_seconds=90) is False


@pytest.mark.anyio
async def test_redis_set_nx_fails_open_when_redis_unavailable():
    mock_client = AsyncMock()
    mock_client.set.side_effect = RedisError("Connection lost")

    provider = RedisCacheProvider(client=mock_client)

    # Fail-open: processing is allowed rather than silently dropping work.
    assert await provider.set_nx("inbox:msg-4", b"PROCESSING", ttl_seconds=90) is True


@pytest.mark.anyio
async def test_redis_provider_uses_configured_timeouts_and_scan_count(monkeypatch):
    from app.core.cache_config import CacheSettings

    settings = CacheSettings(
        redis_socket_connect_timeout_seconds=4.5,
        redis_socket_timeout_seconds=6.5,
        redis_health_check_interval_seconds=45,
        redis_scan_count=7,
    )

    mock_client = AsyncMock()
    mock_client.ping.return_value = True

    captured: dict[str, object] = {}

    def fake_from_url(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return mock_client

    monkeypatch.setattr("app.common.cache.redis.Redis.from_url", fake_from_url)

    provider = RedisCacheProvider(cache_settings=settings)
    await provider.connect()

    assert captured["socket_connect_timeout"] == 4.5
    assert captured["socket_timeout"] == 6.5
    assert captured["health_check_interval"] == 45

    scanned_counts: list[int] = []

    async def fake_scan_iter(match: str, count: int = 100):
        scanned_counts.append(count)
        yield b"inbox:1"

    mock_client.scan_iter = fake_scan_iter
    await provider.clear_prefix("inbox:")

    assert scanned_counts == [7]
