"""Unit and integration tests for cache providers and ResponseCacheMiddleware."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import ICacheProvider, InMemoryCacheProvider, RedisCacheProvider
from app.core.database import get_db
from app.main import app


# =============================================================================
# 1. InMemoryCacheProvider Unit Tests
# =============================================================================


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

    assert await cache.get("missing:key") is None

    await cache.set("test:bytes", b'{"status":"ok"}')
    assert await cache.get("test:bytes") == b'{"status":"ok"}'

    await cache.set("test:str", '{"hello":"world"}')
    assert await cache.get("test:str") == b'{"hello":"world"}'


@pytest.mark.asyncio
async def test_in_memory_ttl_expiration(monkeypatch):
    """Verify expired keys are evicted on access using monotonic clock."""
    current_time = 1000.0
    monkeypatch.setattr("app.common.cache.memory.time.monotonic", lambda: current_time)

    cache = InMemoryCacheProvider(default_ttl_seconds=10)
    await cache.set("short:lived", b"payload", ttl_seconds=5)

    current_time = 1004.0
    assert await cache.get("short:lived") == b"payload"

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


# =============================================================================
# 2. RedisCacheProvider Unit Tests (Mocked Client & Fail-Open Resilience)
# =============================================================================


@pytest.mark.asyncio
async def test_redis_provider_crud_operations():
    """Verify RedisCacheProvider delegates get, setex, delete, scan_iter, and ping."""
    mock_client = AsyncMock()
    mock_client.ping.return_value = True
    mock_client.get.return_value = b'{"cached":true}'
    mock_client.delete.return_value = 2

    async def fake_scan_iter(match: str, count: int = 100):
        for k in [b"catalog:laptop:1", b"catalog:laptop:2"]:
            yield k

    mock_client.scan_iter = fake_scan_iter

    provider = RedisCacheProvider(client=mock_client, default_ttl_seconds=120)
    await provider.connect()
    assert await provider.health_check() is True

    await provider.set("catalog:laptop:1", b'{"cached":true}', ttl_seconds=60)
    mock_client.setex.assert_awaited_once_with(name="catalog:laptop:1", time=60, value=b'{"cached":true}')

    val = await provider.get("catalog:laptop:1")
    assert val == b'{"cached":true}'

    await provider.delete("catalog:laptop:1")
    mock_client.delete.assert_awaited_with("catalog:laptop:1")

    evicted = await provider.clear_prefix("catalog:laptop:")
    assert evicted == 2

    await provider.close()
    mock_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_provider_fail_open_on_errors():
    """Verify RedisCacheProvider fails open without raising exceptions when Redis fails."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = RedisError("Connection lost")
    mock_client.setex.side_effect = RedisError("Connection lost")
    mock_client.delete.side_effect = RedisError("Connection lost")
    mock_client.ping.side_effect = RedisError("Connection lost")

    provider = RedisCacheProvider(client=mock_client)

    assert await provider.get("any:key") is None
    await provider.set("any:key", b"data", ttl_seconds=30)
    await provider.delete("any:key")
    assert await provider.health_check() is False


# =============================================================================
# 3. ResponseCacheMiddleware End-to-End Route Tests
# =============================================================================


@pytest.mark.asyncio
async def test_middleware_caches_get_laptop_detail_and_sets_headers(db_session: AsyncSession):
    """GET /api/v1/laptops/{id} returns MISS on 1st call and HIT on 2nd identical call."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.state.cache = InMemoryCacheProvider(default_ttl_seconds=300)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1st request -> MISS
        r1 = await client.get("/api/v1/laptops/laptop_msi_prestige_9s713q222261")
        assert r1.status_code == 200
        assert r1.headers.get("X-Cache") == "MISS"
        assert "X-Cache-Key" in r1.headers
        assert "X-Cache-Lookup-Time-Ms" in r1.headers
        key_1 = r1.headers["X-Cache-Key"]

        # 2nd identical request -> HIT
        r2 = await client.get("/api/v1/laptops/laptop_msi_prestige_9s713q222261")
        assert r2.status_code == 200
        assert r2.headers.get("X-Cache") == "HIT"
        assert r2.headers.get("X-Cache-Key") == key_1
        assert r2.json() == r1.json()

    app.dependency_overrides.clear()
    app.state.cache = None


@pytest.mark.asyncio
async def test_middleware_strict_100_percent_matching_on_post_recommendations(db_session: AsyncSession):
    """Only 100% identical requests hit the same cache entry; any small change creates a new entry."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.state.cache = InMemoryCacheProvider(default_ttl_seconds=300)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        raw_payload_1 = b'{"budget": 50000, "persona": "student_and_office", "top_k": 3}'

        # 1. First request with raw_payload_1 -> MISS
        resp1 = await client.post(
            "/api/v1/recommendations",
            content=raw_payload_1,
            headers={"Content-Type": "application/json"},
        )
        assert resp1.status_code == 200
        assert resp1.headers["X-Cache"] == "MISS"
        key_1 = resp1.headers["X-Cache-Key"]

        # 2. Second 100% identical request -> HIT on key_1
        resp2 = await client.post(
            "/api/v1/recommendations",
            content=raw_payload_1,
            headers={"Content-Type": "application/json"},
        )
        assert resp2.status_code == 200
        assert resp2.headers["X-Cache"] == "HIT"
        assert resp2.headers["X-Cache-Key"] == key_1
        assert resp2.json() == resp1.json()

        # 3. Small change in budget (50000 -> 50001) -> MISS, new entry key_2
        raw_payload_2 = b'{"budget": 50001, "persona": "student_and_office", "top_k": 3}'
        resp3 = await client.post(
            "/api/v1/recommendations",
            content=raw_payload_2,
            headers={"Content-Type": "application/json"},
        )
        assert resp3.status_code == 200
        assert resp3.headers["X-Cache"] == "MISS"
        key_2 = resp3.headers["X-Cache-Key"]
        assert key_2 != key_1

        # 4. Small change in key order -> MISS, new entry key_3
        raw_payload_3 = b'{"persona": "student_and_office", "budget": 50000, "top_k": 3}'
        resp4 = await client.post(
            "/api/v1/recommendations",
            content=raw_payload_3,
            headers={"Content-Type": "application/json"},
        )
        assert resp4.status_code == 200
        assert resp4.headers["X-Cache"] == "MISS"
        key_3 = resp4.headers["X-Cache-Key"]
        assert key_3 != key_1
        assert key_3 != key_2

    app.dependency_overrides.clear()
    app.state.cache = None


@pytest.mark.asyncio
async def test_middleware_does_not_cache_404_or_422_errors(db_session: AsyncSession):
    """Error responses (404, 422) must never be stored in cache."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    cache = InMemoryCacheProvider(default_ttl_seconds=300)
    app.state.cache = cache

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_404 = await client.get("/api/v1/laptops/non_existent_laptop_id_999")
        assert r_404.status_code == 404
        assert r_404.headers.get("X-Cache") == "MISS"

        r_422 = await client.post("/api/v1/recommendations", json={"persona": "gaming"})
        assert r_422.status_code == 422
        assert r_422.headers.get("X-Cache") == "MISS"

        assert len(cache._store) == 0

    app.dependency_overrides.clear()
    app.state.cache = None
