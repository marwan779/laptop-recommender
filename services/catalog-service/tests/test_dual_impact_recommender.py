"""Tests for the 10-criteria Dual-Impact TOPSIS pipeline and zero-candidate fallback."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from unittest.mock import MagicMock

import httpx
import pytest

from app.domain.recommender import (
    IS_BENEFIT_CRITERION,
    PERSONA_CONFIGS,
    TOPSIS_CRITERIA_KEYS,
    PersonaType,
    parse_user_text_prompt,
    rank_laptops_topsis,
)
from app.schemas.recommendation import RecommendationRequest
from app.services.ai_recommender_client import HttpAIRecommenderClient
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


class _FakeAIRecommenderClient:
    """Test double exposing the remote AI recommender client contract."""

    def __init__(self, response_payload: dict | None) -> None:
        self.response_payload = response_payload
        self.calls: list[dict] = []

    async def recommend(
        self,
        *,
        request: RecommendationRequest,
        primary_persona: PersonaType,
        blended_weights: dict[str, float] | None,
        candidate_laptops: list[dict],
    ) -> dict | None:
        self.calls.append(
            {
                "prompt": request.user_text_prompt,
                "persona": primary_persona,
                "blended_weights": blended_weights,
                "candidate_ids": [c.get("canonical_id") for c in candidate_laptops],
            }
        )
        return self.response_payload


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

    experiential = parse_user_text_prompt("عايز لاب تبريده قوي ومفصلاته متينة ومبيسخنش")
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
    assert (
        adjusted.effective_weights["community_nlp_score"]
        > PERSONA_CONFIGS["balanced"]["weights"]["community_nlp_score"]
    )

    # The domain engine must never mutate the caller's catalog dictionaries.
    assert laptops[0]["derived_metrics"]["topsis_inputs"]["community_nlp_score"] == 80.0
    assert laptops[1]["derived_metrics"]["topsis_inputs"]["community_nlp_score"] == 75.0


@pytest.mark.asyncio
async def test_recommendation_service_delegates_prompt_to_ai_client_and_hydrates_sql_fields():
    laptop_a = _build_laptop("candidate-a", 60000.0)
    laptop_a["offers"] = [
        {
            "store_key": "test-store",
            "store_name": "Test Store",
            "price_egp": 60000.0,
            "product_url": "https://example.com/a",
            "in_stock": True,
            "is_cheapest": True,
        }
    ]
    laptop_a["cheapest_offer_url"] = "https://example.com/a"
    laptop_a["derived_metrics"]["community_reviews"] = {
        "community_nlp_score": 88.0,
        "evidence_count": 14,
        "pros_en": ["Quiet fans"],
        "pros_ar": ["مراوح هادئة"],
        "cons_en": ["Heavy brick"],
        "cons_ar": ["شاحن ثقيل"],
        "aspect_scores": {"acoustics_score": 91.0},
    }
    laptops = [laptop_a, _build_laptop("candidate-b", 60000.0)]

    remote_payload = {
        "persona": "balanced",
        "persona_label_ar": "متوازن",
        "persona_label_en": "Balanced",
        "gates_relaxed_for_low_budget": False,
        "total_candidates_before_floor": 2,
        "total_candidates_after_gates_and_floor": 2,
        "applied_budget_window_egp": [0.0, 100000.0],
        "parsed_text_prompt": {"matched_keywords": ["quiet"]},
        "effective_weights": {"community_nlp_score": 0.25},
        "status": "OK",
        "results": [
            {
                "rank": 1,
                "canonical_id": "candidate-a",
                "brand": "TestBrand",
                "title": "Test Laptop candidate-a",
                "topsis_match_score": 94.2,
                "effective_price_egp": 60000.0,
                "cheapest_store": "test-store",
                "available_stores": ["test-store"],
                "prices_by_store": {"test-store": 60000.0},
                "why_recommended_ar": ["تبريد هادئ"],
                "why_recommended_en": ["Quiet cooling"],
                "topsis_inputs": {"community_nlp_score": 98.0},
            }
        ],
    }
    fake_client = _FakeAIRecommenderClient(remote_payload)
    service = RecommendationService(session=None, ai_client=fake_client)
    service._load_fallback_catalog = lambda: laptops  # type: ignore[method-assign]

    response = await service.get_recommendations(
        RecommendationRequest(
            budget_egp=100000.0,
            persona="balanced",
            user_text_prompt="quiet fans and solid hinges",
            top_k=2,
        )
    )

    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["prompt"] == "quiet fans and solid hinges"
    assert fake_client.calls[0]["candidate_ids"] == ["candidate-a", "candidate-b"]
    assert len(response.results) == 1
    winner = response.results[0]
    assert winner.canonical_id == "candidate-a"
    assert winner.topsis_match_score == 94.2
    assert winner.cheapest_offer_url == "https://example.com/a"
    assert len(winner.offers) == 1
    assert winner.pros_en == ["Quiet fans"]
    assert winner.reviews_evidence_count == 14
    assert winner.aspect_scores == {"acoustics_score": 91.0}


@pytest.mark.asyncio
async def test_recommendation_service_falls_back_to_local_topsis_when_ai_client_returns_none():
    laptops = [
        _build_laptop("candidate-a", 60000.0, nlp_score=92.0),
        _build_laptop("candidate-b", 60000.0, nlp_score=65.0),
    ]
    fake_client = _FakeAIRecommenderClient(None)
    service = RecommendationService(session=None, ai_client=fake_client)
    service._load_fallback_catalog = lambda: laptops  # type: ignore[method-assign]

    response = await service.get_recommendations(
        RecommendationRequest(
            budget_egp=100000.0,
            persona="balanced",
            user_text_prompt="quiet fans and solid hinges",
            top_k=2,
        )
    )

    assert len(fake_client.calls) == 1
    assert response.status == "OK"
    assert len(response.results) == 2
    assert response.results[0].canonical_id == "candidate-a"
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
# 4. HTTP AI RECOMMENDER CLIENT
# =============================================================================


@pytest.mark.asyncio
async def test_http_ai_recommender_client_sends_api_key_and_serializes_dates():
    captured: dict = {}

    class _FakeHttpClient:
        async def post(self, url: str, json: dict, headers: dict):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"status": "OK", "results": []}
            return resp

    client = HttpAIRecommenderClient(
        base_url="http://ai-recommender:8002/",
        api_key="secret-inter-service-key",
        client=_FakeHttpClient(),  # type: ignore[arg-type]
    )
    cand = _build_laptop("candidate-a", 60000.0)
    cand["offers"] = [{"store_key": "sigma", "last_checked_at": datetime(2026, 11, 15, tzinfo=timezone.utc)}]

    result = await client.recommend(
        request=RecommendationRequest(budget_egp=80000.0, persona="balanced", user_text_prompt="quiet fans"),
        primary_persona=PersonaType.BALANCED,
        blended_weights=None,
        candidate_laptops=[cand],
    )

    assert result == {"status": "OK", "results": []}
    assert captured["url"] == "http://ai-recommender:8002/recommend"
    assert captured["headers"]["X-API-Key"] == "secret-inter-service-key"
    assert captured["json"]["candidate_laptops"][0]["offers"][0]["last_checked_at"] == "2026-11-15T00:00:00+00:00"


@pytest.mark.asyncio
async def test_http_ai_recommender_client_omits_api_key_header_when_unset():
    captured: dict = {}

    class _FakeHttpClient:
        async def post(self, url: str, json: dict, headers: dict):
            captured["headers"] = headers
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"status": "OK", "results": []}
            return resp

    client = HttpAIRecommenderClient(
        base_url="http://ai-recommender:8002",
        api_key="",
        client=_FakeHttpClient(),  # type: ignore[arg-type]
    )

    result = await client.recommend(
        request=RecommendationRequest(budget_egp=80000.0, persona="balanced"),
        primary_persona=PersonaType.BALANCED,
        blended_weights=None,
        candidate_laptops=[_build_laptop("candidate-a", 60000.0)],
    )

    assert result == {"status": "OK", "results": []}
    assert "X-API-Key" not in captured["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_http_ai_recommender_client_logs_auth_warning_without_leaking_key(
    status_code: int, caplog: pytest.LogCaptureFixture
):
    secret = "super-secret-inter-service-key"
    request = httpx.Request("POST", "http://ai-recommender:8002/recommend")
    response = httpx.Response(status_code, request=request)
    error = httpx.HTTPStatusError("rejected", request=request, response=response)

    class _FailingHttpClient:
        async def post(self, url: str, json: dict, headers: dict):
            raise error

    client = HttpAIRecommenderClient(
        base_url="http://ai-recommender:8002",
        api_key=secret,
        client=_FailingHttpClient(),  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.WARNING, logger="catalog.services.ai_recommender_client"):
        result = await client.recommend(
            request=RecommendationRequest(budget_egp=80000.0, persona="balanced"),
            primary_persona=PersonaType.BALANCED,
            blended_weights=None,
            candidate_laptops=[_build_laptop("candidate-a", 60000.0)],
        )

    assert result is None
    assert "AI_RECOMMENDER_API_KEY" in caplog.text
    assert str(status_code) in caplog.text
    assert secret not in caplog.text
