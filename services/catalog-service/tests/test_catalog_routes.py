"""Integration tests for the catalog laptop detail API routes."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.services.catalog_query_service import CatalogQueryService


@pytest.mark.asyncio
async def test_get_laptop_detail_by_canonical_id_success(db_session: AsyncSession):
    """Querying by canonical_id returns 200 OK with full 35+ hardware specs, offers, and metrics."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/laptops/laptop_msi_prestige_9s713q222261")
        assert resp.status_code == 200
        data = resp.json()

        # Identity & presentation
        assert data["canonical_id"] == "laptop_msi_prestige_9s713q222261"
        assert data["brand"] == "MSI"
        assert "MSI Prestige" in data["laptop_model"]
        assert data["min_price_egp"] > 0
        assert data["cheapest_store"] in ["compumarts", "sigma", "elbadr"]

        # 35+ Structured Hardware Dimensions
        assert data["cpu"]["manufacturer"] == "Intel"
        assert data["cpu"]["cores"] > 0
        assert data["cpu"]["threads"] > 0

        assert "gpu" in data
        assert data["gpu"]["manufacturer"] != ""

        assert data["memory"]["capacity_gb"] >= 8
        assert data["memory"]["memory_type"] != ""

        assert data["storage"]["capacity_gb"] >= 256
        assert data["storage"]["storage_type"] == "SSD"

        assert data["display"]["size_inches"] > 0
        assert data["display"]["width"] > 0
        assert data["display"]["height"] > 0
        assert data["display"]["refresh_rate_hz"] >= 60

        assert "power_battery" in data
        assert "physical" in data
        assert "build_security" in data
        assert "audio_webcam" in data
        assert "connectivity_os" in data

        # Live Offers with direct URLs and freshness
        assert len(data["offers"]) >= 1
        first_offer = data["offers"][0]
        assert first_offer["store_key"] != ""
        assert first_offer["price_egp"] > 0
        assert first_offer["product_url"].startswith("http")
        assert first_offer["last_checked_at"] is not None
        assert data["price_checked_at"] is not None

        # Metrics
        assert data["metrics"] is not None
        assert data["metrics"]["cpu_score"] > 0
        assert data["metrics"]["gpu_score"] >= 0

        # Bilingual Explanations
        assert len(data["why_recommended_ar"]) >= 1
        assert len(data["why_recommended_en"]) >= 1

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_laptop_detail_by_uuid_success(db_session: AsyncSession):
    """Querying by database UUID resolves correctly."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First retrieve by canonical_id to get its UUID
        init_resp = await client.get("/api/v1/laptops/laptop_msi_prestige_9s713q222261")
        assert init_resp.status_code == 200
        lap_id = init_resp.json()["id"]

        # Now query by UUID
        resp = await client.get(f"/api/v1/laptops/{lap_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == lap_id
        assert data["canonical_id"] == "laptop_msi_prestige_9s713q222261"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_laptop_detail_by_mpn_success(db_session: AsyncSession):
    """Querying by manufacturer part number (MPN) resolves correctly."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First retrieve by canonical_id to get its MPN
        init_resp = await client.get("/api/v1/laptops/laptop_msi_prestige_9s713q222261")
        assert init_resp.status_code == 200
        mpn = init_resp.json()["mpn"]
        assert mpn is not None

        # Now query by MPN
        resp = await client.get(f"/api/v1/laptops/{mpn}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["canonical_id"] == "laptop_msi_prestige_9s713q222261"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_catalog_laptop_detail_alias(db_session: AsyncSession):
    """The alias route /api/v1/catalog/laptops/{laptop_id} also works."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/catalog/laptops/laptop_msi_prestige_9s713q222261")
        assert resp.status_code == 200
        assert resp.json()["canonical_id"] == "laptop_msi_prestige_9s713q222261"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_laptop_detail_not_found(db_session: AsyncSession):
    """Querying a non-existent laptop returns 404 Not Found."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/laptops/non_existent_laptop_id_123456")
        assert resp.status_code == 404
        body = resp.json()
        assert "not found" in str(body).lower()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_catalog_query_service_offline_fallback():
    """CatalogQueryService works even without database session via local JSON fallback."""
    service = CatalogQueryService(session=None)
    result = await service.get_laptop_detail("laptop_msi_prestige_9s713q222261")
    assert result.canonical_id == "laptop_msi_prestige_9s713q222261"
    assert result.min_price_egp == 47999.0
    assert result.cpu.manufacturer == "Intel"
    assert len(result.offers) >= 1


@pytest.mark.asyncio
async def test_list_laptops_paginated_with_review_fields(db_session: AsyncSession):
    """The catalog browse endpoint returns paginated cards with review intelligence."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/laptops?offset=0&limit=5")
        assert resp.status_code == 200
        data = resp.json()

        assert data["offset"] == 0
        assert data["limit"] == 5
        assert data["total"] >= 5
        assert len(data["items"]) == 5
        assert data["total"] >= len(data["items"])

        item = data["items"][0]
        for field in (
            "id",
            "canonical_id",
            "brand",
            "laptop_model",
            "title",
            "min_price_egp",
            "cheapest_store",
            "ram_capacity_gb",
            "storage_capacity_gb",
            "gpu_model",
            "cpu_model",
            "display_size_inches",
            "community_nlp_score",
            "value_score",
            "has_reviews",
            "reviews_evidence_count",
            "pros_ar",
            "pros_en",
            "cons_ar",
            "cons_en",
        ):
            assert field in item

        assert isinstance(item["community_nlp_score"], float)
        assert isinstance(item["reviews_evidence_count"], int)
        assert isinstance(item["pros_ar"], list)

        reviewed_item = next(
            (candidate for candidate in data["items"] if candidate["has_reviews"]),
            None,
        )
        if reviewed_item is not None:
            assert reviewed_item["reviews_evidence_count"] >= 0
            assert reviewed_item["community_nlp_score"] >= 0.0

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_laptops_price_and_brand_filters(db_session: AsyncSession):
    """Price and brand query parameters strictly constrain catalog results."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/laptops?brand=ASUS&max_price=90000&limit=100")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        for item in data["items"]:
            assert item["brand"].upper() == "ASUS"
            assert item["min_price_egp"] <= 90000.0

        alias_resp = await client.get("/api/v1/catalog/laptops?limit=2")
        assert alias_resp.status_code == 200
        assert len(alias_resp.json()["items"]) == 2

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_catalog_query_service_list_laptops_offline_fallback():
    """Catalog browse still works from the local JSON catalog without a DB session."""
    service = CatalogQueryService(session=None)
    result = await service.list_laptops(limit=10, offset=0)

    assert result.total > 0
    assert len(result.items) == 10
    assert result.items[0].canonical_id
    assert result.items[0].min_price_egp > 0


@pytest.mark.asyncio
async def test_list_laptops_metric_filter_narrows_results(db_session: AsyncSession):
    """Metric gates only return laptops meeting every requested minimum score."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        baseline = await client.get("/api/v1/laptops?limit=100&in_stock_only=false")
        assert baseline.status_code == 200
        base_items = baseline.json()["items"]
        gpu_scores = [
            item["metric_scores"]["gpu_score"]
            for item in base_items
            if "gpu_score" in item.get("metric_scores", {})
        ]
        assert gpu_scores, "Expected at least one laptop with a GPU score"

        threshold = sorted(gpu_scores)[len(gpu_scores) // 2]
        filtered = await client.get(
            f"/api/v1/laptops?limit=100&in_stock_only=false&min_gpu_score={threshold}"
        )
        assert filtered.status_code == 200
        data = filtered.json()
        assert data["total"] >= 1
        assert data["total"] <= baseline.json()["total"]
        for item in data["items"]:
            assert item["metric_scores"]["gpu_score"] >= threshold

        out_of_range = await client.get("/api/v1/laptops?min_gpu_score=150")
        assert out_of_range.status_code == 422

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_catalog_query_service_metric_fallback_filter():
    """Offline fallback applies the same metric gates without a database session."""
    service = CatalogQueryService(session=None)
    baseline = await service.list_laptops(limit=100, in_stock_only=False)
    assert baseline.items

    thermals = [
        item.metric_scores["thermals_score"]
        for item in baseline.items
        if "thermals_score" in item.metric_scores
    ]
    assert thermals, "Expected fallback laptops to expose aspect scores"

    threshold = sorted(thermals)[len(thermals) // 2]
    filtered = await service.list_laptops(
        limit=100,
        in_stock_only=False,
        min_thermals_score=threshold,
    )

    assert filtered.total >= 1
    assert filtered.total <= baseline.total
    for item in filtered.items:
        assert item.metric_scores["thermals_score"] >= threshold
