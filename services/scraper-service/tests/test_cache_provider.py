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
