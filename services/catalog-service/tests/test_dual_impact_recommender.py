"""Tests for the 10-criteria Dual-Impact TOPSIS pipeline and zero-candidate fallback."""

from __future__ import annotations

import pytest

from app.domain.recommender import (
    IS_BENEFIT_CRITERION,
    PERSONA_CONFIGS,
    TOPSIS_CRITERIA_KEYS,
    parse_user_text_prompt,
    rank_laptops_topsis,
)
from app.schemas.recommendation import RecommendationRequest
from app.services.chroma_reviews_service import (
    ChromaReviewsService,
    get_chroma_reviews_service,
)
from app.services.recommendation_service import RecommendationService


def _build_laptop(
    canonical_id: str,
    price_egp: float,
    nlp_score: float = 75.0,
    cpu_score: float = 85.0,
    gpu_score: float = 85.0,
    brand: str = "TestBrand",
) -> dict:
    """Build a minimal normalized laptop dict compatible with the TOPSIS engine."""
    topsis_inputs = {
        "cpu_score": cpu_score,
        "gpu_score": gpu_score,
        "power_therm_score": 80.0,
        "display_score": 80.0,
        "mobility_score": 80.0,
        "longevity_score": 80.0,
        "ergonomics_score": 80.0,
        "connectivity_score": 80.0,
        "community_nlp_score": nlp_score,
        "effective_price_egp": price_egp,
        "in_stock_active": True,
        "is_recommendable_price": True,
        "value_score": 80.0,
    }
    return {
        "canonical_id": canonical_id,
        "brand": brand,
        "title": f"Test Laptop {canonical_id}",
        "thumbnail_url": None,
        "cheapest_store": "test-store",
        "available_stores": ["test-store"],
        "prices_by_store": {"test-store": price_egp},
        "urls_by_store": {"test-store": "https://example.com"},
        "offers": [],
        "derived_metrics": {
            "topsis_inputs": topsis_inputs,
            "community_reviews": {"community_nlp_score": nlp_score},
        },
        "specs": {
            "memory": {"capacity_gb": 16},
            "storage": {"capacity_gb": 1024},
            "gpu": {"integrated": False},
            "cpu": {"cores": 8},
            "display": {"refresh_rate_hz": 144, "panel_type": "IPS", "touchscreen": False},
        },
    }


class _FakeChromaService:
    """Test double exposing the singleton service query contract."""

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.calls: list[str] = []

    def query_dual_similarity(self, user_query: str) -> dict[str, float]:
        self.calls.append(user_query)
        return dict(self.scores)


# =============================================================================
# 1. 10-CRITERIA PERSONA CONFIGURATION
# =============================================================================


def test_topsis_uses_ten_criteria_with_community_nlp_as_benefit():
    assert len(TOPSIS_CRITERIA_KEYS) == 10
    assert TOPSIS_CRITERIA_KEYS[8] == "community_nlp_score"
    assert TOPSIS_CRITERIA_KEYS[-1] == "effective_price_egp"
    assert len(IS_BENEFIT_CRITERION) == 10
    assert IS_BENEFIT_CRITERION[:9] == [True] * 9
    assert IS_BENEFIT_CRITERION[9] is False


@pytest.mark.parametrize("persona", list(PERSONA_CONFIGS.keys()))
def test_persona_weights_cover_all_criteria_and_sum_to_one(persona: str):
    weights = PERSONA_CONFIGS[persona]["weights"]

    assert set(weights) == set(TOPSIS_CRITERIA_KEYS)
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert weights["community_nlp_score"] == pytest.approx(0.06)


# =============================================================================
# 2. DUAL-IMPACT PROMPT PARSING & CHROMA SCORE OVERRIDES
# =============================================================================


def test_prompt_applies_baseline_and_experiential_review_boost():
    generic = parse_user_text_prompt("I want a fast laptop for coding")
    assert generic["weight_boosts"]["community_nlp_score"] == pytest.approx(0.08)

    experiential = parse_user_text_prompt(
        "عايز لاب تبريده قوي ومفصلاته متينة ومبيسخنش"
    )
    assert experiential["weight_boosts"]["community_nlp_score"] == pytest.approx(0.14)


def test_chroma_adjusted_scores_reorder_candidates_and_boost_review_weight():
    laptops = [
        _build_laptop("candidate-a", 60000.0, nlp_score=80.0),
        _build_laptop("candidate-b", 60000.0, nlp_score=75.0),
    ]

    baseline = rank_laptops_topsis(
        laptops=laptops,
        max_budget_egp=100000.0,
        persona="balanced",
        apply_smart_60pct_floor=False,
        top_k=2,
    )
    assert baseline.results[0].canonical_id == "candidate-a"

    prompt = "عايز لاب تبريده قوي ومفصلاته متينة ومبيسخنش"
    adjusted = rank_laptops_topsis(
        laptops=laptops,
        max_budget_egp=100000.0,
        persona="balanced",
        user_text_prompt=prompt,
        apply_smart_60pct_floor=False,
        top_k=2,
        chroma_adjusted_nlp_scores={"candidate-a": 35.0, "candidate-b": 98.0},
    )

    assert adjusted.results[0].canonical_id == "candidate-b"
    assert adjusted.results[0].topsis_inputs["community_nlp_score"] == 98.0
    assert adjusted.effective_weights["community_nlp_score"] > PERSONA_CONFIGS["balanced"][
        "weights"
    ]["community_nlp_score"]

    # The domain engine must never mutate the caller's catalog dictionaries.
    assert laptops[0]["derived_metrics"]["topsis_inputs"]["community_nlp_score"] == 80.0
    assert laptops[1]["derived_metrics"]["topsis_inputs"]["community_nlp_score"] == 75.0


@pytest.mark.asyncio
async def test_recommendation_service_applies_chroma_scores_to_response():
    laptops = [
        _build_laptop("candidate-a", 60000.0),
        _build_laptop("candidate-b", 60000.0),
    ]
    fake_chroma = _FakeChromaService({"candidate-a": 98.0, "candidate-b": 35.0})

    service = RecommendationService(session=None, chroma_service=fake_chroma)
    service._load_fallback_catalog = lambda: laptops  # type: ignore[method-assign]

    response = await service.get_recommendations(
        RecommendationRequest(
            budget_egp=100000.0,
            persona="balanced",
            user_text_prompt="quiet fans and solid hinges",
            top_k=2,
        )
    )

    assert fake_chroma.calls == ["quiet fans and solid hinges"]
    by_id = {result.canonical_id: result for result in response.results}
    assert by_id["candidate-a"].topsis_inputs["community_nlp_score"] == 98.0
    assert by_id["candidate-b"].topsis_inputs["community_nlp_score"] == 35.0
    assert response.status == "OK"
    assert response.effective_weights["community_nlp_score"] > 0.06


# =============================================================================
# 3. ZERO-CANDIDATE FALLBACK
# =============================================================================


def test_zero_candidate_budget_returns_three_cheapest_alternatives():
    laptops = [
        _build_laptop("price-30k", 30000.0),
        _build_laptop("price-25k", 25000.0),
        _build_laptop("price-40k", 40000.0),
        _build_laptop("price-50k", 50000.0),
        _build_laptop("price-60k", 60000.0),
    ]

    result = rank_laptops_topsis(
        laptops=laptops,
        max_budget_egp=18000.0,
        persona="gaming",
        top_k=10,
    )

    assert result.status == "BUDGET_TOO_LOW_FOR_CATEGORY"
    assert result.gates_relaxed_for_low_budget is True
    assert len(result.results) == 3
    assert {item.canonical_id for item in result.results} == {
        "price-25k",
        "price-30k",
        "price-40k",
    }


def test_zero_candidate_with_empty_catalog_returns_empty_results():
    result = rank_laptops_topsis(
        laptops=[],
        max_budget_egp=18000.0,
        persona="gaming",
        top_k=10,
    )

    assert result.status == "BUDGET_TOO_LOW_FOR_CATEGORY"
    assert result.results == []
    assert result.total_candidates_after_gates_and_floor == 0


def test_zero_candidate_fallback_respects_existing_brand_filter():
    laptops = [
        _build_laptop("asus-25k", 25000.0, brand="ASUS"),
        _build_laptop("asus-30k", 30000.0, brand="ASUS"),
        _build_laptop("lenovo-20k", 20000.0, brand="Lenovo"),
    ]

    result = rank_laptops_topsis(
        laptops=laptops,
        max_budget_egp=18000.0,
        persona="balanced",
        brand_filter=["ASUS"],
        top_k=10,
    )

    assert result.status == "BUDGET_TOO_LOW_FOR_CATEGORY"
    assert {item.brand for item in result.results} == {"ASUS"}
    assert len(result.results) == 2


# =============================================================================
# 4. SINGLETON LIFECYCLE
# =============================================================================


def test_chroma_reviews_service_is_a_process_wide_singleton():
    ChromaReviewsService.reset_singleton()

    first = get_chroma_reviews_service()
    second = get_chroma_reviews_service()

    assert first is second
    assert ChromaReviewsService() is first

    ChromaReviewsService.reset_singleton()
