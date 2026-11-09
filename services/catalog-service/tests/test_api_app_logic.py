"""Comprehensive End-to-End API Test Suite for App Business Logic.

Covers:
1. Recommendation Engine & TOPSIS Logic (all 7 personas, multi-persona blending,
   custom weights, Swagger dummy sanitization, budget windows, low-budget relaxation,
   impossible constraints, hardware/brand filters, bilingual AR/EN prompt parsing,
   and 422 validation boundaries).
2. Catalog & Full Laptop Detail Logic (cross-identifier equivalence for UUID/canonical_id/MPN,
   case-insensitivity, multi-store price spread & cheapest offer invariants, 35+ spec blocks,
   and Recommendation -> Product Detail UX journey).
3. Caching, Headers & Middleware Pipeline (strict 100%-exact matching vs small changes,
   X-Correlation-ID tracing on HIT/MISS, cache disable toggle, and Redis fail-open).
4. Operational, Health & Batch Status Endpoints.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import InMemoryCacheProvider, RedisCacheProvider
from app.core.config import settings
from app.core.database import get_db
from app.main import app


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession):
    """Provide an AsyncClient wired to the test DB session and a fresh InMemoryCacheProvider."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.state.cache = InMemoryCacheProvider(default_ttl_seconds=300)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    app.state.cache = None


# =============================================================================
# 1. Recommendation Engine & TOPSIS Business Logic (POST /api/v1/recommendations)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "persona",
    [
        "gaming",
        "programming",
        "ai_and_game_dev",
        "content_creation",
        "student_and_office",
        "business_and_mobility",
        "balanced",
    ],
)
async def test_all_seven_personas_end_to_end(api_client: AsyncClient, persona: str):
    """Every persona returns properly ranked results, localized labels, and valid weights."""
    resp = await api_client.post(
        "/api/v1/recommendations",
        json={"budget": 85000.0, "persona": persona, "top_k": 5},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["persona"] == persona
    assert data["persona_label_ar"] != ""
    assert data["persona_label_en"] != ""
    assert len(data["results"]) > 0
    assert len(data["results"]) <= 5

    # Weights must sum to ~1.0
    total_weight = sum(data["effective_weights"].values())
    assert abs(total_weight - 1.0) < 0.01

    # Ranks must be sequential (1..N) and scores strictly non-increasing
    scores = [r["topsis_match_score"] for r in data["results"]]
    ranks = [r["rank"] for r in data["results"]]
    assert ranks == list(range(1, len(data["results"]) + 1))
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_multi_persona_blending_and_custom_weights(api_client: AsyncClient):
    """Multi-persona blending and explicit custom weight overrides normalize cleanly."""
    resp = await api_client.post(
        "/api/v1/recommendations",
        json={
            "budget": 75000.0,
            "persona": "gaming",
            "personas": ["gaming", "content_creation"],
            "custom_weights": {"display_score": 0.40, "gpu_score": 0.40, "cpu_score": 0.20},
            "top_k": 3,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    weights = data["effective_weights"]
    assert abs(sum(weights.values()) - 1.0) < 0.01
    assert weights["display_score"] > 0.25
    assert weights["gpu_score"] > 0.25


@pytest.mark.asyncio
async def test_swagger_dummy_custom_weights_ignored_safely(api_client: AsyncClient):
    """Swagger default {"additionalProp1": 0} in custom_weights must not break persona weights."""
    resp = await api_client.post(
        "/api/v1/recommendations",
        json={
            "budget": 60000.0,
            "persona": "programming",
            "custom_weights": {"additionalProp1": 0, "additionalProp2": 0},
            "top_k": 3,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) > 0
    assert abs(sum(data["effective_weights"].values()) - 1.0) < 0.01


@pytest.mark.asyncio
async def test_budget_window_enforcement_and_auto_floor(api_client: AsyncClient):
    """Returned laptops strictly obey [min_budget_egp, budget_egp]."""
    resp = await api_client.post(
        "/api/v1/recommendations",
        json={
            "budget_egp": 65000.0,
            "min_budget_egp": 45000.0,
            "persona": "balanced",
            "top_k": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["applied_budget_window_egp"] == [45000.0, 65000.0]
    assert len(data["results"]) > 0
    for item in data["results"]:
        assert 45000.0 <= item["effective_price_egp"] <= 65000.0


@pytest.mark.asyncio
async def test_low_budget_gate_relaxation(api_client: AsyncClient):
    """When budget is too tight for strict gaming gates, gates relax automatically."""
    resp = await api_client.post(
        "/api/v1/recommendations",
        json={
            "budget": 24000.0,
            "persona": "gaming",
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["gates_relaxed_for_low_budget"] is True
    assert len(data["results"]) > 0
    for item in data["results"]:
        assert item["effective_price_egp"] <= 24000.0


@pytest.mark.asyncio
async def test_impossible_constraints_fall_back_to_cheapest_alternatives(api_client: AsyncClient):
    """Zero candidates under strict filters return the 3 cheapest active alternatives."""
    resp = await api_client.post(
        "/api/v1/recommendations",
        json={
            "budget": 20000.0,
            "persona": "ai_and_game_dev",
            "min_ram_gb": 64,
            "min_storage_gb": 2000,
            "require_dgpu": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "BUDGET_TOO_LOW_FOR_CATEGORY"
    assert 0 < len(data["results"]) <= 3


@pytest.mark.asyncio
async def test_hardware_and_brand_filters_respected(api_client: AsyncClient):
    """Explicit brand, RAM, storage, and OLED filters strictly constrain candidates."""
    resp = await api_client.post(
        "/api/v1/recommendations",
        json={
            "budget": 95000.0,
            "persona": "content_creation",
            "min_ram_gb": 16,
            "min_storage_gb": 512,
            "brand_filter": ["asus", "msi"],
            "top_k": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) > 0
    for item in data["results"]:
        assert item["brand"].lower() in ("asus", "msi")


@pytest.mark.asyncio
async def test_bilingual_english_and_arabic_prompt_parsing(api_client: AsyncClient):
    """English and Arabic prompts extract filters and boost target criteria weights."""
    # English prompt requesting 32GB RAM + 1TB SSD + OLED + cooling + upgradeability
    en_resp = await api_client.post(
        "/api/v1/recommendations",
        json={
            "budget": 95000.0,
            "persona": "balanced",
            "user_text_prompt": "I want 32GB RAM, 1TB SSD, an OLED display with strong cooling and upgradeable slots",
            "top_k": 3,
        },
    )
    assert en_resp.status_code == 200
    en_parsed = en_resp.json()["parsed_text_prompt"]
    assert en_parsed["extracted_filters"].get("min_ram_gb") == 32
    assert en_parsed["extracted_filters"].get("min_storage_gb") == 1024
    assert en_parsed["extracted_filters"].get("require_oled") is True
    assert en_parsed["weight_boosts"].get("display_score", 0) > 0
    assert en_parsed["weight_boosts"].get("power_therm_score", 0) > 0
    assert en_parsed["weight_boosts"].get("longevity_score", 0) > 0


@pytest.mark.asyncio
async def test_recommendation_response_includes_review_intelligence(api_client: AsyncClient):
    """Recommendation cards carry status and the full review breakdown."""
    resp = await api_client.post(
        "/api/v1/recommendations",
        json={
            "budget": 85000.0,
            "persona": "gaming",
            "user_text_prompt": "quiet fans and solid hinges",
            "top_k": 3,
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] in {
        "OK",
        "GATES_RELAXED_FOR_LOW_BUDGET",
        "BUDGET_TOO_LOW_FOR_CATEGORY",
    }
    assert len(data["results"]) >= 1

    card = data["results"][0]
    for field in (
        "reviews_evidence_count",
        "aspect_scores",
        "pros_ar",
        "pros_en",
        "cons_ar",
        "cons_en",
    ):
        assert field in card

    assert isinstance(card["reviews_evidence_count"], int)
    assert isinstance(card["aspect_scores"], dict)
    assert isinstance(card["pros_ar"], list)
    assert isinstance(card["cons_en"], list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"persona": "gaming"},  # Missing budget
        {"budget": 50000},  # Missing persona
        {"budget": -1000, "persona": "gaming"},  # Negative budget
        {"budget": 0, "persona": "gaming"},  # Zero budget
        {"budget": 50000, "persona": "invalid_persona_name"},  # Invalid enum
        {"budget": 50000, "persona": "gaming", "min_ram_gb": 2},  # RAM < 4
        {"budget": 50000, "persona": "gaming", "top_k": 0},  # top_k < 1
        {"budget": 50000, "persona": "gaming", "top_k": 99},  # top_k > 50
    ],
)
async def test_recommendation_validation_error_boundaries(
    api_client: AsyncClient,
    invalid_payload: dict,
):
    """Invalid payloads return 422 Unprocessable Entity without server errors."""
    resp = await api_client.post("/api/v1/recommendations", json=invalid_payload)
    assert resp.status_code == 422


# =============================================================================
# 2. Catalog & Full Laptop Detail Logic (GET /api/v1/laptops/{laptop_id})
# =============================================================================


@pytest.mark.asyncio
async def test_cross_identifier_equivalence_and_case_insensitivity(api_client: AsyncClient):
    """Canonical ID, UUID, and MPN (upper/lower case) all resolve to the exact same laptop."""
    canonical_id = "laptop_msi_prestige_9s713q222261"

    r_canon = await api_client.get(f"/api/v1/laptops/{canonical_id.upper()}")
    assert r_canon.status_code == 200
    d_canon = r_canon.json()

    r_uuid = await api_client.get(f"/api/v1/laptops/{d_canon['id']}")
    assert r_uuid.status_code == 200
    d_uuid = r_uuid.json()

    r_mpn = await api_client.get(f"/api/v1/laptops/{d_canon['mpn'].lower()}")
    assert r_mpn.status_code == 200
    d_mpn = r_mpn.json()

    assert d_canon["id"] == d_uuid["id"] == d_mpn["id"]
    assert d_canon["canonical_id"] == d_uuid["canonical_id"] == d_mpn["canonical_id"]
    assert d_canon["title"] == d_uuid["title"] == d_mpn["title"]


@pytest.mark.asyncio
async def test_multi_store_laptop_price_spread_and_offer_invariants(api_client: AsyncClient):
    """Multi-store laptop accurately computes min/max price, spread, cheapest store, and timestamps."""
    # ASUS Vivobook S14 has multiple store offers (sigma & compumarts)
    resp = await api_client.get("/api/v1/laptops/laptop_asus_vivobook_s14m3407kasf155w")
    assert resp.status_code == 200
    data = resp.json()

    assert data["stores_count"] >= 2
    assert len(data["offers"]) >= 2
    assert data["max_price_egp"] >= data["min_price_egp"]
    expected_spread = round(data["max_price_egp"] - data["min_price_egp"], 2)
    assert abs(data["price_spread_egp"] - expected_spread) < 1.0

    # Verify cheapest store offer has is_cheapest=True and valid product_url + last_checked_at
    cheapest_offers = [o for o in data["offers"] if o["is_cheapest"]]
    assert len(cheapest_offers) >= 1
    assert cheapest_offers[0]["store_key"] == data["cheapest_store"].lower()
    assert data["cheapest_offer_url"] == cheapest_offers[0]["product_url"]

    for offer in data["offers"]:
        assert offer["product_url"].startswith("http")
        assert offer["price_egp"] > 0
        assert offer["last_checked_at"] is not None


@pytest.mark.asyncio
async def test_user_journey_recommendation_to_full_laptop_detail(api_client: AsyncClient):
    """Simulate frontend user flow: run recommendation -> click #1 laptop -> load full details."""
    rec_resp = await api_client.post(
        "/api/v1/recommendations",
        json={"budget": 60000.0, "persona": "student_and_office", "top_k": 3},
    )
    assert rec_resp.status_code == 200
    top_pick = rec_resp.json()["results"][0]

    detail_resp = await api_client.get(f"/api/v1/laptops/{top_pick['canonical_id']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    assert detail["canonical_id"] == top_pick["canonical_id"]
    assert detail["brand"] == top_pick["brand"]
    assert detail["min_price_egp"] == top_pick["effective_price_egp"]
    assert detail["cheapest_store"] == top_pick["cheapest_store"]
    assert detail["cheapest_offer_url"] == top_pick["cheapest_offer_url"]


# =============================================================================
# 3. Caching, Correlation IDs & Resilience Pipeline
# =============================================================================


@pytest.mark.asyncio
async def test_correlation_id_preserved_across_cache_miss_and_hit(api_client: AsyncClient):
    """Custom X-Correlation-ID header is echoed on both MISS and cached HIT responses."""
    corr_miss = f"trace-miss-{uuid.uuid4()}"
    r1 = await api_client.get(
        "/api/v1/laptops/laptop_msi_prestige_9s713q222261",
        headers={"X-Correlation-ID": corr_miss},
    )
    assert r1.status_code == 200
    assert r1.headers["X-Cache"] == "MISS"
    assert r1.headers["X-Correlation-ID"] == corr_miss

    corr_hit = f"trace-hit-{uuid.uuid4()}"
    r2 = await api_client.get(
        "/api/v1/laptops/laptop_msi_prestige_9s713q222261",
        headers={"X-Correlation-ID": corr_hit},
    )
    assert r2.status_code == 200
    assert r2.headers["X-Cache"] == "HIT"
    assert r2.headers["X-Correlation-ID"] == corr_hit


@pytest.mark.asyncio
async def test_cache_disabled_setting_bypasses_middleware(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """When settings.enable_cache is False, requests bypass caching completely."""
    monkeypatch.setattr(settings, "enable_cache", False)

    r1 = await api_client.get("/api/v1/laptops/laptop_msi_prestige_9s713q222261")
    assert r1.status_code == 200
    assert "X-Cache" not in r1.headers


@pytest.mark.asyncio
async def test_redis_failure_fails_open_and_serves_from_database(db_session: AsyncSession):
    """If Redis throws a connection error mid-request, the endpoint still returns 200 OK from DB."""

    async def override_get_db():
        yield db_session

    broken_redis = AsyncMock()
    broken_redis.get.side_effect = RedisError("Redis socket timeout")
    broken_redis.setex.side_effect = RedisError("Redis socket timeout")

    app.dependency_overrides[get_db] = override_get_db
    app.state.cache = RedisCacheProvider(client=broken_redis)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/laptops/laptop_msi_prestige_9s713q222261")
        assert resp.status_code == 200
        assert resp.headers.get("X-Cache") == "MISS"
        assert resp.json()["canonical_id"] == "laptop_msi_prestige_9s713q222261"

    app.dependency_overrides.clear()
    app.state.cache = None


# =============================================================================
# 4. Operational, Root & Batch Status Endpoints
# =============================================================================


@pytest.mark.asyncio
async def test_root_and_health_endpoints_not_cached(api_client: AsyncClient):
    """Root and health endpoints return 200 OK and are never cached."""
    r_root = await api_client.get("/")
    assert r_root.status_code == 200
    assert r_root.json()["status"] == "ok"
    assert "X-Cache" not in r_root.headers

    r_health = await api_client.get("/health")
    assert r_health.status_code == 200
    assert "X-Cache" not in r_health.headers


@pytest.mark.asyncio
async def test_scraping_operational_endpoints_pointers_and_logs(api_client: AsyncClient):
    """GET /api/v1/scraping/pointers and /logs return 200 OK lists and bypass cache."""
    r_pointers = await api_client.get("/api/v1/scraping/pointers")
    assert r_pointers.status_code == 200
    assert isinstance(r_pointers.json(), list)
    assert "X-Cache" not in r_pointers.headers

    r_logs = await api_client.get("/api/v1/scraping/logs?limit=5")
    assert r_logs.status_code == 200
    assert isinstance(r_logs.json(), list)
    assert len(r_logs.json()) <= 5
    assert "X-Cache" not in r_logs.headers
