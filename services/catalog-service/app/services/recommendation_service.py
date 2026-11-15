"""Recommendation Application Service.

Orchestrates data retrieval from the repository layer and delegates multi-criteria
ranking and explainability to the domain TOPSIS recommender engine.
"""

import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.logger import get_logger
from app.common.review_text import align_bilingual_lists
from app.domain.recommender import (
    PERSONA_CONFIGS,
    TOPSIS_CRITERIA_KEYS,
    PersonaType,
    TopsisExecutionResult,
    parse_user_text_prompt,
    rank_laptops_topsis,
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

# Maps optional recommendation request metric gates to their score location:
# ``(source_container, score_key)``.
_METRIC_FILTER_SOURCES: dict[str, tuple[str, str]] = {
    "min_acoustics_score": ("aspect_scores", "acoustics_score"),
    "min_thermals_score": ("aspect_scores", "thermals_score"),
    "min_battery_score": ("aspect_scores", "real_battery_and_reliability_score"),
    "min_build_score": ("aspect_scores", "build_and_hinges_score"),
    "min_keyboard_score": ("aspect_scores", "keyboard_and_trackpad_score"),
    "min_cpu_score": ("topsis_inputs", "cpu_score"),
    "min_gpu_score": ("topsis_inputs", "gpu_score"),
    "min_display_score": ("topsis_inputs", "display_score"),
    "min_value_score": ("topsis_inputs", "value_score"),
}


def _metric_score(lap: dict[str, Any], source: str, key: str) -> float | None:
    """Read one metric score from a recommender dict without raising on gaps."""
    derived = lap.get("derived_metrics") or {}
    if source == "aspect_scores":
        container = (derived.get("community_reviews") or {}).get("aspect_scores") or derived.get("aspect_scores")
    else:
        container = derived.get(source)
    if not isinstance(container, dict):
        return None

    raw = container.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def _passes_request_metric_filters(lap: dict[str, Any], request: RecommendationRequest) -> bool:
    """Return True when a candidate satisfies every optional metric gate."""
    for filter_name, (source, key) in _METRIC_FILTER_SOURCES.items():
        threshold = getattr(request, filter_name, None)
        if threshold is None:
            continue
        score = _metric_score(lap, source, key)
        if score is None or score < threshold:
            return False
    return True


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
    """Application use-case service for TOPSIS laptop recommendations."""

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
        """Fetch candidates, apply persona weighting, and execute dynamic TOPSIS."""
        candidate_dicts: list[dict[str, Any]] = []

        if self.session is not None:
            repo = LaptopRepository(self.session)
            # Load the full active catalog (unbounded by budget) so the domain
            # engine can apply budget windows and still return the cheapest
            # alternatives when the requested category has zero candidates.
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

        # Graceful fallback to file if database has no rows (e.g. testing)
        if not candidate_dicts:
            candidate_dicts = self._load_fallback_catalog()

        # Optional real-world experience / hardware metric gates are applied
        # before TOPSIS normalization so the decision matrix only contains
        # candidates that satisfy every requested minimum.
        candidate_dicts = [
            lap for lap in candidate_dicts if _passes_request_metric_filters(lap, request)
        ]

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

        # Remote semantic recommendation: when a free-text prompt is present,
        # delegate to ai-recommender-service (Jina-v3 Chroma + TOPSIS) using the
        # live PostgreSQL candidate_dicts, falling back cleanly to local TOPSIS
        # if the remote service is unavailable or returns no results.
        if request.user_text_prompt and request.user_text_prompt.strip():
            remote_payload = await self._resolve_ai_client().recommend(
                request=request,
                primary_persona=primary_persona,
                blended_weights=blended_weights,
                candidate_laptops=candidate_dicts,
            )
            if isinstance(remote_payload, dict) and remote_payload.get("results"):
                return self._map_ai_response_to_recommendation_response(
                    remote_payload=remote_payload,
                    request=request,
                    primary_persona=primary_persona,
                    blended_weights=blended_weights,
                    candidate_dicts=candidate_dicts,
                )

        # Execute pure domain TOPSIS engine (local fast path & remote fallback)
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

    def _map_ai_response_to_recommendation_response(
        self,
        *,
        remote_payload: dict[str, Any],
        request: RecommendationRequest,
        primary_persona: PersonaType,
        blended_weights: dict[str, float] | None,
        candidate_dicts: list[dict[str, Any]],
    ) -> RecommendationResponse:
        """Map ai-recommender-service payload + SQL candidate metadata into RecommendationResponse."""
        p_cfg = PERSONA_CONFIGS.get(primary_persona, PERSONA_CONFIGS[PersonaType.BALANCED])
        p_key = primary_persona.value if hasattr(primary_persona, "value") else str(primary_persona)
        candidates_by_id = {
            str(c.get("canonical_id")): c for c in candidate_dicts if c.get("canonical_id")
        }

        fallback_weights = blended_weights or dict(p_cfg["weights"])
        raw_weights = remote_payload.get("effective_weights")
        effective_weights = (
            {str(k): float(v) for k, v in raw_weights.items()}
            if isinstance(raw_weights, dict) and raw_weights
            else fallback_weights
        )

        raw_budget_window = remote_payload.get("applied_budget_window_egp")
        applied_budget_window = (
            [float(x) for x in raw_budget_window]
            if isinstance(raw_budget_window, list) and len(raw_budget_window) == 2
            else [float(request.min_budget_egp or 0.0), float(request.budget_egp)]
        )

        parsed_prompt = remote_payload.get("parsed_text_prompt")
        if not isinstance(parsed_prompt, dict):
            parsed_prompt = parse_user_text_prompt(request.user_text_prompt or "")

        ranked_responses: list[RankedLaptopResponse] = []
        for idx, item in enumerate(remote_payload.get("results") or [], start=1):
            if not isinstance(item, dict):
                continue
            cid = str(item.get("canonical_id") or "")
            cand = candidates_by_id.get(cid, {})
            cand_comm = ((cand.get("derived_metrics") or {}).get("community_reviews") or {})
            item_comm = item.get("community_reviews") if isinstance(item.get("community_reviews"), dict) else {}

            raw_aspect = item.get("aspect_scores") or item_comm.get("aspect_scores") or cand_comm.get("aspect_scores") or {}
            aspect_scores = (
                {str(k): float(v) for k, v in raw_aspect.items() if v is not None}
                if isinstance(raw_aspect, dict)
                else {}
            )

            urls_by_store = dict(item.get("urls_by_store") or cand.get("urls_by_store") or {})
            cheapest_store = str(item.get("cheapest_store") or cand.get("cheapest_store") or "unknown")
            cheapest_offer_url = (
                item.get("cheapest_offer_url")
                or cand.get("cheapest_offer_url")
                or urls_by_store.get(cheapest_store.lower().strip())
            )
            raw_offers = item.get("offers") if item.get("offers") is not None else (cand.get("offers") or [])

            evidence_raw = (
                item.get("reviews_evidence_count")
                if item.get("reviews_evidence_count") is not None
                else (item_comm.get("evidence_count") if item_comm.get("evidence_count") is not None else cand_comm.get("evidence_count", 0))
            )
            try:
                evidence_count = max(0, int(evidence_raw or 0))
            except (TypeError, ValueError):
                evidence_count = 0

            ranked_responses.append(
                RankedLaptopResponse(
                    rank=int(item.get("rank") or idx),
                    canonical_id=cid,
                    brand=str(item.get("brand") or cand.get("brand") or "Generic"),
                    laptop_family=item.get("laptop_family") or cand.get("laptop_family"),
                    laptop_model=item.get("laptop_model") or cand.get("laptop_model"),
                    title=str(item.get("title") or cand.get("title") or "Laptop"),
                    thumbnail_url=item.get("thumbnail_url") or cand.get("thumbnail_url"),
                    topsis_match_score=float(item.get("topsis_match_score") or 0.0),
                    effective_price_egp=float(item.get("effective_price_egp") or cand.get("effective_price_egp") or 0.0),
                    cheapest_store=cheapest_store,
                    cheapest_offer_url=cheapest_offer_url,
                    available_stores=list(item.get("available_stores") or cand.get("available_stores") or []),
                    prices_by_store={
                        str(k): float(v)
                        for k, v in (item.get("prices_by_store") or cand.get("prices_by_store") or {}).items()
                    },
                    urls_by_store=urls_by_store,
                    offers=_to_store_offer_responses(raw_offers),
                    why_recommended_ar=list(item.get("why_recommended_ar") or []),
                    why_recommended_en=list(item.get("why_recommended_en") or []),
                    pros_en=list(item.get("pros_en") or item_comm.get("pros_en") or cand_comm.get("pros_en") or []),
                    pros_ar=list(item.get("pros_ar") or item_comm.get("pros_ar") or cand_comm.get("pros_ar") or []),
                    cons_en=list(item.get("cons_en") or item_comm.get("cons_en") or cand_comm.get("cons_en") or []),
                    cons_ar=list(item.get("cons_ar") or item_comm.get("cons_ar") or cand_comm.get("cons_ar") or []),
                    reviews_evidence_count=evidence_count,
                    aspect_scores=aspect_scores,
                    topsis_inputs=dict(item.get("topsis_inputs") or {}),
                )
            )

        return RecommendationResponse(
            persona=str(remote_payload.get("persona") or p_key),
            persona_label_ar=str(remote_payload.get("persona_label_ar") or p_cfg["label_ar"]),
            persona_label_en=str(remote_payload.get("persona_label_en") or p_cfg["label_en"]),
            gates_relaxed_for_low_budget=bool(remote_payload.get("gates_relaxed_for_low_budget", False)),
            total_candidates_before_floor=int(
                remote_payload.get("total_candidates_before_floor", len(candidate_dicts))
            ),
            total_candidates_after_gates_and_floor=int(
                remote_payload.get("total_candidates_after_gates_and_floor", len(ranked_responses))
            ),
            applied_budget_window_egp=applied_budget_window,
            parsed_text_prompt=parsed_prompt,
            effective_weights=effective_weights,
            results=ranked_responses,
            status=str(remote_payload.get("status") or "OK"),
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
