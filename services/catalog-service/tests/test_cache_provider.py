"""Unit tests for the cache provider contract and InMemoryCacheProvider."""

import pytest

from app.common.cache import ICacheProvider, InMemoryCacheProvider


def test_in_memory_provider_implements_contract():
    """Verify InMemoryCacheProvider adheres to ICacheProvider ABC."""
    assert issubclass(InMemoryCacheProvider, ICacheProvider)
    provider = InMemoryCacheProvider()
    assert isinstance(provider, ICacheProvider)


@pytest.mark.asyncio
async def test_in_memory_set_and_get():
    """Verify storing and retrieving bytes and strings."""
    cache = InMemoryCacheProvider(default_ttl_seconds=60)
    await cache.connect()
    assert await cache.health_check() is True

    # Miss on unknown key
    assert await cache.get("missing:key") is None

    # Set bytes
    await cache.set("test:bytes", b'{"status":"ok"}')
    assert await cache.get("test:bytes") == b'{"status":"ok"}'

    # Set string (auto-encoded to utf-8 bytes)
    await cache.set("test:str", '{"hello":"world"}')
    assert await cache.get("test:str") == b'{"hello":"world"}'


@pytest.mark.asyncio
async def test_in_memory_ttl_expiration(monkeypatch):
    """Verify expired keys are evicted on access using monotonic clock."""
    current_time = 1000.0
    monkeypatch.setattr("app.common.cache.memory.time.monotonic", lambda: current_time)

    cache = InMemoryCacheProvider(default_ttl_seconds=10)
    await cache.set("short:lived", b"payload", ttl_seconds=5)

    # Before expiration (t = 1004.0)
    current_time = 1004.0
    assert await cache.get("short:lived") == b"payload"

    # At/After expiration (t = 1005.1)
    current_time = 1005.1
    assert await cache.get("short:lived") is None


@pytest.mark.asyncio
async def test_in_memory_delete_and_clear_prefix():
    """Verify single key deletion and prefix-based bulk eviction."""
    cache = InMemoryCacheProvider()
    await cache.set("catalog:laptop:1", b"lap1")
    await cache.set("catalog:laptop:2", b"lap2")
    await cache.set("catalog:recommendation:abc", b"rec1")

    await cache.delete("catalog:laptop:1")
    assert await cache.get("catalog:laptop:1") is None
    assert await cache.get("catalog:laptop:2") == b"lap2"

    evicted = await cache.clear_prefix("catalog:laptop:")
    assert evicted == 1
    assert await cache.get("catalog:laptop:2") is None
    assert await cache.get("catalog:recommendation:abc") == b"rec1"


@pytest.mark.asyncio
async def test_in_memory_close_clears_and_marks_unhealthy():
    """Verify closing the provider clears state and marks health_check False."""
    cache = InMemoryCacheProvider()
    await cache.set("k1", b"v1")
    await cache.close()

    assert await cache.health_check() is False
    assert await cache.get("k1") is None
