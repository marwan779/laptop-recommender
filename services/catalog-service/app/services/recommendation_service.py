"""Recommendation Application Service.

Orchestrates data retrieval from the repository layer and delegates multi-criteria
ranking and explainability to the domain TOPSIS recommender engine.
"""

import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.logger import get_logger
from app.domain.recommender import (
    PERSONA_CONFIGS,
    TOPSIS_CRITERIA_KEYS,
    PersonaType,
    TopsisExecutionResult,
    rank_laptops_topsis,
)
from app.repositories.laptop_repository import LaptopRepository, to_recommender_dict
from app.schemas.recommendation import (
    RankedLaptopResponse,
    RecommendationRequest,
    RecommendationResponse,
    StoreOfferResponse,
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

        is_cheapest = (store_k == cheapest_store)
        if is_cheapest and p_url and not cheapest_offer_url:
            cheapest_offer_url = p_url

        clean_offers.append({
            "store_key": store_k,
            "store_name": off.get("store_name") or store_k,
            "price_egp": float(p_egp) if p_egp is not None else 0.0,
            "product_url": p_url or "",
            "in_stock": in_stock,
            "is_cheapest": is_cheapest,
            "last_checked_at": off.get("last_checked_at") or off.get("last_checked") or off.get("scraped_at"),
            "price_updated_at": off.get("price_updated_at") or off.get("scraped_at"),
        })

    if not cheapest_offer_url and urls_by_store:
        cheapest_offer_url = urls_by_store.get(cheapest_store) or next(iter(urls_by_store.values()), None)

    lap["prices_by_store"] = prices_by_store
    lap["urls_by_store"] = urls_by_store
    lap["cheapest_offer_url"] = cheapest_offer_url
    lap["offers"] = clean_offers
    return lap


class RecommendationService:
    """Application use-case service for TOPSIS laptop recommendations."""

    def __init__(self, session: AsyncSession | None = None):
        self.session = session
        self._fallback_catalog: list[dict[str, Any]] | None = None

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
        """Fetch candidates, apply persona weighting, and execute dynamic TOPSIS."""
        candidate_dicts: list[dict[str, Any]] = []

        if self.session is not None:
            repo = LaptopRepository(self.session)
            db_candidates = await repo.get_candidates_for_recommendation(
                max_budget_egp=request.budget_egp,
                brand_filter=request.brand_filter,
            )
            if db_candidates:
                candidate_dicts = [to_recommender_dict(c) for c in db_candidates]

        # Graceful fallback to file if database has no rows (e.g. testing)
        if not candidate_dicts:
            candidate_dicts = self._load_fallback_catalog()

        # Resolve primary persona
        primary_persona = request.persona or (request.personas[0] if request.personas else PersonaType.BALANCED)

        # Multi-persona weight blending if user selected multiple personas
        blended_weights: dict[str, float] | None = None
        if request.personas and len(request.personas) > 1:
            blended_weights = {}
            for key in TOPSIS_CRITERIA_KEYS:
                avg_w = sum(
                    PERSONA_CONFIGS.get(p, PERSONA_CONFIGS[PersonaType.BALANCED])["weights"].get(key, 0.1)
                    for p in request.personas
                ) / len(request.personas)
                blended_weights[key] = round(avg_w, 4)

        # If user also provided custom_weights, override on top of blended/persona weights
        if request.custom_weights:
            blended_weights = blended_weights or dict(
                PERSONA_CONFIGS.get(primary_persona, PERSONA_CONFIGS[PersonaType.BALANCED])["weights"]
            )
            for k, v in request.custom_weights.items():
                if k in blended_weights and v is not None:
                    blended_weights[k] = float(v)

        # Execute pure domain TOPSIS engine
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
            custom_weights=blended_weights,
            top_k=request.top_k,
        )

        # Map domain dataclasses to Pydantic presentation response
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
                effective_price_egp=r.effective_price_egp,
                cheapest_store=r.cheapest_store,
                cheapest_offer_url=r.cheapest_offer_url,
                available_stores=r.available_stores,
                prices_by_store=r.prices_by_store,
                urls_by_store=r.urls_by_store,
                offers=[
                    StoreOfferResponse(
                        store_key=o.get("store_key", "generic"),
                        store_name=o.get("store_name", o.get("store_key", "Store")),
                        price_egp=float(o.get("price_egp", 0.0)),
                        product_url=o.get("product_url", ""),
                        in_stock=bool(o.get("in_stock", True)),
                        is_cheapest=bool(o.get("is_cheapest", False)),
                        last_checked_at=o.get("last_checked_at"),
                    )
                    for o in r.offers
                ],
                why_recommended_ar=r.why_recommended_ar,
                why_recommended_en=r.why_recommended_en,
                pros_en=r.pros_en,
                pros_ar=r.pros_ar,
                cons_en=r.cons_en,
                cons_ar=r.cons_ar,
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
        )
