"""Recommendation Application Service.

Orchestrates data retrieval from the repository layer, optional lightweight
prompt scoring via ai-recommender-service (``POST /score-prompt``), and
local 14-column domain TOPSIS ranking.
"""

import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.logger import get_logger
from app.common.review_text import align_bilingual_lists
from app.domain.recommender import (
    PersonaType,
    TopsisExecutionResult,
    rank_laptops_topsis,
    resolve_persona_key,
)
from app.repositories.laptop_repository import LaptopRepository, to_recommender_dict
from app.schemas.recommendation import (
    RankedLaptopResponse,
    RecommendationRequest,
    RecommendationResponse,
    StoreOfferResponse,
)
from app.services.ai_recommender_client import (
    HttpAIRecommenderClient,
    IAIRecommenderClient,
)

logger = get_logger("catalog.services.recommendation")

FALLBACK_CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "scraping input" / "unified_catalog_latest.json"


def _normalize_catalog_dict(lap: dict[str, Any]) -> dict[str, Any]:
    """Ensure raw catalog dictionary has complete urls_by_store, cheapest_offer_url, and offers."""
    cheapest_store = str(lap.get("cheapest_store") or "unknown").lower().strip()
    prices_by_store = dict(lap.get("prices_by_store") or {})
    urls_by_store = dict(lap.get("urls_by_store") or {})
    raw_offers = list(lap.get("offers") or [])
    cheapest_offer_url = lap.get("cheapest_offer_url")

    clean_offers = []
    for off in raw_offers:
        store_k = str(off.get("store_key") or "generic").lower().strip()
        p_url = off.get("product_url")
        p_egp = off.get("price_egp")
        in_stock = bool(off.get("in_stock", True))
        is_valid = bool(off.get("is_valid_price", True))

        if p_url:
            urls_by_store[store_k] = p_url
        if p_egp is not None and is_valid:
            prices_by_store[store_k] = float(p_egp)

        is_cheapest = store_k == cheapest_store
        if is_cheapest and p_url and not cheapest_offer_url:
            cheapest_offer_url = p_url

        clean_offers.append(
            {
                "store_key": store_k,
                "store_name": off.get("store_name") or store_k,
                "price_egp": float(p_egp) if p_egp is not None else 0.0,
                "product_url": p_url or "",
                "in_stock": in_stock,
                "is_cheapest": is_cheapest,
                "last_checked_at": off.get("last_checked_at") or off.get("last_checked") or off.get("scraped_at"),
                "price_updated_at": off.get("price_updated_at") or off.get("scraped_at"),
            }
        )

    if not cheapest_offer_url and urls_by_store:
        cheapest_offer_url = urls_by_store.get(cheapest_store) or next(iter(urls_by_store.values()), None)

    lap["prices_by_store"] = prices_by_store
    lap["urls_by_store"] = urls_by_store
    lap["cheapest_offer_url"] = cheapest_offer_url
    lap["offers"] = clean_offers

    comm = (lap.get("derived_metrics") or {}).get("community_reviews")
    if isinstance(comm, dict):
        p_en, p_ar = align_bilingual_lists(comm.get("pros_en"), comm.get("pros_ar"))
        c_en, c_ar = align_bilingual_lists(comm.get("cons_en"), comm.get("cons_ar"))
        comm["pros_en"] = p_en
        comm["pros_ar"] = p_ar
        comm["cons_en"] = c_en
        comm["cons_ar"] = c_ar

    return lap


class RecommendationService:
    """Application use-case service for 14-column TOPSIS laptop recommendations."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        ai_client: IAIRecommenderClient | None = None,
    ):
        self.session = session
        self.ai_client = ai_client
        self._fallback_catalog: list[dict[str, Any]] | None = None

    def _resolve_ai_client(self) -> IAIRecommenderClient:
        if self.ai_client is None:
            self.ai_client = HttpAIRecommenderClient()
        return self.ai_client

    def _load_fallback_catalog(self) -> list[dict[str, Any]]:
        if self._fallback_catalog is None:
            if FALLBACK_CATALOG_PATH.exists():
                try:
                    with open(FALLBACK_CATALOG_PATH, encoding="utf-8") as f:
                        data = json.load(f)
                    raw_laptops = data.get("laptops", [])
                    self._fallback_catalog = [_normalize_catalog_dict(l) for l in raw_laptops]
                    logger.info("Loaded %d laptops from fallback catalog JSON.", len(self._fallback_catalog))
                except Exception as exc:
                    logger.warning("Could not load fallback catalog JSON: %s", exc)
                    self._fallback_catalog = []
            else:
                self._fallback_catalog = []
        return self._fallback_catalog

    async def get_recommendations(
        self,
        request: RecommendationRequest,
    ) -> RecommendationResponse:
        """Fetch candidates, optionally score prompt via ai-recommender-service, and run local TOPSIS."""
        candidate_dicts: list[dict[str, Any]] = []

        if self.session is not None:
            repo = LaptopRepository(self.session)
            db_candidates = await repo.get_candidates_for_recommendation(
                max_budget_egp=None,
                brand_filter=request.brand_filter,
            )
            if not db_candidates and request.brand_filter:
                db_candidates = await repo.get_candidates_for_recommendation(
                    max_budget_egp=None,
                    brand_filter=None,
                )
            if db_candidates:
                candidate_dicts = [to_recommender_dict(c) for c in db_candidates]

        if not candidate_dicts:
            candidate_dicts = self._load_fallback_catalog()

        primary_persona = resolve_persona_key(request.persona or PersonaType.BALANCED)

        adjusted_nlp_scores: dict[str, float] | None = None
        nlp_dynamic_weight: float | None = None
        parsed_constraints: dict[str, Any] | None = None

        if request.user_text_prompt and request.user_text_prompt.strip():
            score_payload = await self._resolve_ai_client().score_prompt(request.user_text_prompt.strip())
            if isinstance(score_payload, dict):
                raw_scores = score_payload.get("adjusted_nlp_scores")
                if isinstance(raw_scores, dict):
                    adjusted_nlp_scores = {
                        str(k): float(v) for k, v in raw_scores.items() if v is not None
                    }
                raw_dyn_w = score_payload.get("nlp_dynamic_weight")
                if isinstance(raw_dyn_w, (int, float)) and not isinstance(raw_dyn_w, bool):
                    nlp_dynamic_weight = float(raw_dyn_w)
                raw_constraints = score_payload.get("parsed_constraints")
                if isinstance(raw_constraints, dict):
                    parsed_constraints = dict(raw_constraints)

        domain_result: TopsisExecutionResult = rank_laptops_topsis(
            laptops=candidate_dicts,
            max_budget_egp=request.budget_egp,
            min_budget_egp=request.min_budget_egp,
            persona=primary_persona,
            user_text_prompt=request.user_text_prompt,
            min_ram_gb=request.min_ram_gb,
            min_storage_gb=request.min_storage_gb,
            require_dgpu=request.require_dgpu,
            brand_filter=request.brand_filter,
            custom_weights=request.custom_weights,
            nlp_dynamic_weight=nlp_dynamic_weight,
            chroma_adjusted_nlp_scores=adjusted_nlp_scores,
            parsed_constraints=parsed_constraints,
            top_k=request.top_k,
        )

        ranked_responses = [
            RankedLaptopResponse(
                rank=r.rank,
                canonical_id=r.canonical_id,
                brand=r.brand,
                laptop_family=r.laptop_family,
                laptop_model=r.laptop_model,
                title=r.title,
                thumbnail_url=r.thumbnail_url,
                topsis_match_score=r.topsis_match_score,
                persona_value_score=r.persona_value_score,
                effective_price_egp=r.effective_price_egp,
                cheapest_store=r.cheapest_store,
                cheapest_offer_url=r.cheapest_offer_url,
                available_stores=r.available_stores,
                prices_by_store=r.prices_by_store,
                urls_by_store=r.urls_by_store,
                offers=_to_store_offer_responses(r.offers),
                why_recommended_ar=r.why_recommended_ar,
                why_recommended_en=r.why_recommended_en,
                pros_en=r.pros_en,
                pros_ar=r.pros_ar,
                cons_en=r.cons_en,
                cons_ar=r.cons_ar,
                reviews_evidence_count=r.reviews_evidence_count,
                aspect_scores=r.aspect_scores,
                topsis_inputs=r.topsis_inputs,
            )
            for r in domain_result.results
        ]

        return RecommendationResponse(
            persona=domain_result.persona,
            persona_label_ar=domain_result.persona_label_ar,
            persona_label_en=domain_result.persona_label_en,
            gates_relaxed_for_low_budget=domain_result.gates_relaxed_for_low_budget,
            total_candidates_before_floor=domain_result.total_candidates_before_floor,
            total_candidates_after_gates_and_floor=domain_result.total_candidates_after_gates_and_floor,
            applied_budget_window_egp=domain_result.applied_budget_window_egp,
            parsed_text_prompt=domain_result.parsed_text_prompt,
            effective_weights=domain_result.effective_weights,
            results=ranked_responses,
            status=domain_result.status,
        )


def _to_store_offer_responses(raw_offers: list[dict[str, Any]]) -> list[StoreOfferResponse]:
    """Convert raw offer dicts into validated StoreOfferResponse models."""
    return [
        StoreOfferResponse(
            store_key=o.get("store_key", "generic"),
            store_name=o.get("store_name", o.get("store_key", "Store")),
            price_egp=float(o.get("price_egp", 0.0)),
            product_url=o.get("product_url", ""),
            in_stock=bool(o.get("in_stock", True)),
            is_cheapest=bool(o.get("is_cheapest", False)),
            last_checked_at=o.get("last_checked_at"),
        )
        for o in raw_offers
    ]
