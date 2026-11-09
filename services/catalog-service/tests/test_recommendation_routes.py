"""Integration tests for the recommendations API route."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app


@pytest.mark.asyncio
async def test_recommendations_endpoint_missing_budget_fails():
    """Budget is strictly required; missing it returns 422 Unprocessable Entity."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/recommendations",
            json={"persona": "gaming"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body or "detail" in body


@pytest.mark.asyncio
async def test_recommendations_endpoint_missing_persona_fails():
    """At least one persona must be chosen; missing it returns 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/recommendations",
            json={"budget": 70000.0},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body or "detail" in body


@pytest.mark.asyncio
async def test_recommendations_endpoint_success(db_session: AsyncSession):
    """Happy path with valid budget and persona returns 200 OK with ranked results and product URLs."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/recommendations",
            json={
                "budget": 70000.0,
                "persona": "gaming",
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["persona"] == "gaming"
        assert "الألعاب" in data["persona_label_ar"]
        assert data["total_candidates_before_floor"] > 0
        assert len(data["results"]) > 0

        winner = data["results"][0]
        assert winner["rank"] == 1
        assert winner["effective_price_egp"] <= 70000.0
        assert len(winner["why_recommended_ar"]) > 0
        assert len(winner["why_recommended_en"]) > 0

        # Verify direct product URL & offers for high UX
        assert winner["cheapest_offer_url"] is not None
        assert winner["cheapest_offer_url"].startswith("http")
        assert len(winner["offers"]) > 0
        assert winner["offers"][0]["product_url"].startswith("http")
        assert winner["cheapest_store"] in winner["urls_by_store"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recommendations_endpoint_arabic_prompt(db_session: AsyncSession):
    """Free-text Arabic prompt extracts constraints (OLED) and applies dynamic boosts."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/recommendations",
            json={
                "budget_egp": 55000.0,
                "persona": "programming",
                "user_text_prompt": "عايز بطارية تقعد كتير ووزن خفيف وشاشة اوليد",
                "top_k": 3,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        parsed = data["parsed_text_prompt"]
        assert parsed["extracted_filters"].get("require_oled") is True
        assert parsed["weight_boosts"].get("mobility_score", 0.0) > 0.10
        assert len(data["results"]) > 0
        assert data["results"][0]["cheapest_offer_url"].startswith("http")

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recommendations_endpoint_multiple_personas_blending(db_session: AsyncSession):
    """Passing a list of multiple personas blends criteria weights smoothly."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/recommendations",
            json={
                "max_budget_egp": 80000.0,
                "personas": ["gaming", "programming"],
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["results"]) > 0
        weights = data["effective_weights"]
        assert weights["gpu_score"] > 0.10
        assert weights["cpu_score"] > 0.15

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recommendations_endpoint_brand_filter(db_session: AsyncSession):
    """Brand filter returns only candidate laptops from that brand."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/recommendations",
            json={
                "budget": 90000.0,
                "persona": "balanced",
                "brand_filter": ["ASUS"],
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) > 0
        for r in data["results"]:
            assert r["brand"].upper() == "ASUS"

    app.dependency_overrides.clear()
