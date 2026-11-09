import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.base import utcnow
from app.models.laptop import LaptopConfiguration
from app.repositories.base import BaseRepository

_REVIEW_ASPECT_KEYS: tuple[str, ...] = (
    "thermals_score",
    "acoustics_score",
    "build_and_hinges_score",
    "keyboard_and_trackpad_score",
    "real_battery_and_reliability_score",
)


def _coerce_str_list(value: Any) -> list[str]:
    """Normalize a persisted or incoming review list into clean strings."""
    if not value:
        return []
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        return []
    return [str(item).strip() for item in values if item is not None and str(item).strip()]


def _coerce_optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_review_payload(payload: Any) -> dict[str, Any]:
    """Accept a mapping or DTO, optionally wrapping a ``community_reviews`` block."""
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    if not isinstance(payload, Mapping):
        return {}

    nested = payload.get("community_reviews")
    if isinstance(nested, Mapping):
        return dict(nested)
    return dict(payload)


def to_recommender_dict(laptop: LaptopConfiguration) -> dict[str, Any]:
    """Convert a LaptopConfiguration ORM instance into a domain recommender dictionary."""
    metrics = laptop.metrics
    topsis_inputs = {
        "cpu_score": float(metrics.cpu_score) if metrics and metrics.cpu_score is not None else 50.0,
        "gpu_score": float(metrics.gpu_score) if metrics and metrics.gpu_score is not None else 50.0,
        "power_therm_score": float(metrics.power_therm_score) if metrics and metrics.power_therm_score is not None else 50.0,
        "display_score": float(metrics.display_score) if metrics and metrics.display_score is not None else 50.0,
        "mobility_score": float(metrics.mobility_score) if metrics and metrics.mobility_score is not None else 50.0,
        "longevity_score": float(metrics.longevity_score) if metrics and metrics.longevity_score is not None else 50.0,
        "ergonomics_score": float(metrics.ergonomics_score) if metrics and metrics.ergonomics_score is not None else 50.0,
        "connectivity_score": float(metrics.connectivity_score) if metrics and metrics.connectivity_score is not None else 50.0,
        "community_nlp_score": (
            float(metrics.community_nlp_score)
            if metrics and metrics.community_nlp_score is not None
            else 75.0
        ),
        "effective_price_egp": (
            float(metrics.effective_price_egp)
            if metrics and metrics.effective_price_egp
            else (float(laptop.min_price_egp) if laptop.min_price_egp else 0.0)
        ),
        "value_score": float(metrics.value_score) if metrics and metrics.value_score is not None else 50.0,
        "in_stock_active": bool(metrics.in_stock_active) if metrics and metrics.in_stock_active is not None else bool(laptop.in_stock),
    }

    prices_by_store: dict[str, float] = {}
    urls_by_store: dict[str, str] = {}
    formatted_offers: list[dict[str, Any]] = []
    cheapest_store = str(laptop.cheapest_store or "unknown").lower().strip()
    cheapest_offer_url: str | None = None

    if laptop.offers:
        for offer in laptop.offers:
            if offer.store_key and offer.is_valid_price:
                store_k = offer.store_key.lower().strip()
                if offer.price_egp is not None:
                    prices_by_store[store_k] = float(offer.price_egp)
                if offer.product_url:
                    urls_by_store[store_k] = offer.product_url

                is_cheapest = (store_k == cheapest_store)
                if is_cheapest and offer.product_url and not cheapest_offer_url:
                    cheapest_offer_url = offer.product_url

                formatted_offers.append({
                    "store_key": store_k,
                    "store_name": offer.store_name or store_k,
                    "price_egp": float(offer.price_egp) if offer.price_egp else 0.0,
                    "product_url": offer.product_url or "",
                    "in_stock": bool(offer.in_stock),
                    "is_cheapest": is_cheapest,
                    "last_checked_at": offer.last_checked_at,
                    "price_updated_at": offer.price_updated_at,
                })

    if not cheapest_offer_url and urls_by_store:
        cheapest_offer_url = urls_by_store.get(cheapest_store) or next(iter(urls_by_store.values()), None)

    return {
        "id": str(laptop.id),
        "canonical_id": laptop.canonical_id,
        "mpn": laptop.mpn,
        "brand": laptop.brand,
        "laptop_family": laptop.laptop_family,
        "laptop_model": laptop.laptop_model,
        "title": laptop.title,
        "thumbnail_url": laptop.thumbnail_url,
        "cheapest_store": laptop.cheapest_store or "unknown",
        "cheapest_offer_url": cheapest_offer_url,
        "available_stores": laptop.available_stores or list(prices_by_store.keys()),
        "prices_by_store": prices_by_store,
        "urls_by_store": urls_by_store,
        "offers": formatted_offers,
        "price_spread_egp": float(laptop.price_spread_egp) if laptop.price_spread_egp else 0.0,
        "specs": {
            "identity": {
                "brand": laptop.brand,
                "laptop_family": laptop.laptop_family,
                "laptop_model": laptop.laptop_model,
                "manufacturer_part_number": laptop.mpn,
            },
            "cpu": {
                "manufacturer": laptop.cpu_manufacturer,
                "line": laptop.cpu_line,
                "model": laptop.cpu_model,
                "full_name": laptop.cpu_full_name,
                "cores": laptop.cpu_cores,
                "threads": laptop.cpu_threads,
                "clock_base_ghz": float(laptop.cpu_base_clock_ghz) if laptop.cpu_base_clock_ghz else None,
                "clock_boost_ghz": float(laptop.cpu_boost_clock_ghz) if laptop.cpu_boost_clock_ghz else None,
            },
            "gpu": {
                "manufacturer": laptop.gpu_manufacturer,
                "model": laptop.gpu_model,
                "integrated": bool(laptop.gpu_integrated),
                "vram_gb": laptop.gpu_vram_gb,
                "tdp_w": laptop.gpu_tdp_w,
            },
            "memory": {
                "capacity_gb": laptop.ram_capacity_gb,
                "memory_type": laptop.ram_type,
                "speed": laptop.ram_speed_mhz,
                "slot_count": laptop.ram_slot_count,
                "max_supported_gb": laptop.ram_max_supported_gb,
            },
            "storage": {
                "capacity_gb": laptop.storage_capacity_gb,
                "storage_type": laptop.storage_type,
                "slot_count": laptop.storage_slot_count,
            },
            "display": {
                "size_inches": float(laptop.display_size_inches) if laptop.display_size_inches else 15.6,
                "resolution": laptop.display_resolution,
                "panel_type": laptop.display_panel_type,
                "refresh_rate_hz": laptop.display_refresh_rate_hz,
                "color_gamut": laptop.display_color_gamut,
                "touchscreen": bool(laptop.display_touchscreen),
            },
        },
        "derived_metrics": {
            "silicon": {
                "inferred_tgp_w": float(laptop.gpu_tdp_w) if laptop.gpu_tdp_w else None,
            },
            "display": {
                "panel_technology": laptop.display_panel_type,
                "refresh_rate_hz": laptop.display_refresh_rate_hz,
                "color_gamut_tier": laptop.display_color_gamut or (metrics.display_tier if metrics else ""),
            },
            "mobility": {
                "weight_kg": float(laptop.weight_kg) if laptop.weight_kg else 2.0,
                "battery_hours_estimate": (
                    float(metrics.estimated_battery_hours)
                    if metrics and metrics.estimated_battery_hours
                    else 5.0
                ),
            },
            "longevity": {
                "total_m2_slots": laptop.storage_slot_count or 1,
                "max_ram_gb": laptop.ram_max_supported_gb or laptop.ram_capacity_gb,
            },
            "topsis_inputs": topsis_inputs,
            "community_reviews": {
                "community_nlp_score": topsis_inputs["community_nlp_score"],
                "evidence_count": laptop.reviews_evidence_count or 0,
                "pros_en": list(laptop.pros_en or []),
                "pros_ar": list(laptop.pros_ar or []),
                "cons_en": list(laptop.cons_en or []),
                "cons_ar": list(laptop.cons_ar or []),
                "aspect_scores": {
                    key: (
                        float(getattr(metrics, key))
                        if metrics is not None and getattr(metrics, key, None) is not None
                        else 75.0
                    )
                    for key in _REVIEW_ASPECT_KEYS
                },
            },
        },
    }


class LaptopRepository(BaseRepository[LaptopConfiguration]):
    """Repository handling queries for canonical laptop configurations."""

    def __init__(self, session: AsyncSession):
        super().__init__(LaptopConfiguration, session)

    async def get_by_identifier(self, identifier: str) -> LaptopConfiguration | None:
        """Fetch a laptop configuration by UUID, canonical_id, or mpn with offers and metrics loaded."""
        cleaned_id = identifier.strip()
        parsed_uuid: uuid.UUID | None = None
        try:
            parsed_uuid = uuid.UUID(cleaned_id)
        except (ValueError, AttributeError):
            parsed_uuid = None

        stmt = select(LaptopConfiguration).options(
            selectinload(LaptopConfiguration.offers),
            selectinload(LaptopConfiguration.metrics),
        )

        if parsed_uuid:
            stmt = stmt.where(
                (LaptopConfiguration.id == parsed_uuid)
                | (func.lower(LaptopConfiguration.canonical_id) == cleaned_id.lower())
                | (func.lower(LaptopConfiguration.mpn) == cleaned_id.lower())
            )
        else:
            stmt = stmt.where(
                (func.lower(LaptopConfiguration.canonical_id) == cleaned_id.lower())
                | (func.lower(LaptopConfiguration.mpn) == cleaned_id.lower())
            )

        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_canonical_id(self, canonical_id: str) -> LaptopConfiguration | None:
        stmt = (
            select(LaptopConfiguration)
            .where(LaptopConfiguration.canonical_id == canonical_id)
            .options(
                selectinload(LaptopConfiguration.offers),
                selectinload(LaptopConfiguration.metrics),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_mpn(self, mpn: str) -> LaptopConfiguration | None:
        stmt = (
            select(LaptopConfiguration)
            .where(LaptopConfiguration.mpn == mpn)
            .options(
                selectinload(LaptopConfiguration.offers),
                selectinload(LaptopConfiguration.metrics),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_configurations(
        self,
        min_price: float | None = None,
        max_price: float | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[LaptopConfiguration]:
        stmt = select(LaptopConfiguration).options(
            selectinload(LaptopConfiguration.offers),
            selectinload(LaptopConfiguration.metrics),
        )

        if min_price is not None:
            stmt = stmt.where(LaptopConfiguration.min_price_egp >= min_price)
        if max_price is not None:
            stmt = stmt.where(LaptopConfiguration.min_price_egp <= max_price)

        stmt = stmt.order_by(LaptopConfiguration.min_price_egp.asc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_and_count_configurations(
        self,
        min_price: float | None = None,
        max_price: float | None = None,
        brand: str | None = None,
        in_stock_only: bool = True,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[LaptopConfiguration], int]:
        """Return one catalog page plus the total number of matching configurations."""
        filters: list[Any] = []
        if min_price is not None:
            filters.append(LaptopConfiguration.min_price_egp >= min_price)
        if max_price is not None:
            filters.append(LaptopConfiguration.min_price_egp <= max_price)
        if brand:
            filters.append(func.lower(LaptopConfiguration.brand) == brand.lower().strip())
        if in_stock_only:
            filters.append(LaptopConfiguration.in_stock.is_(True))

        count_stmt = select(func.count()).select_from(LaptopConfiguration).where(*filters)
        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)

        stmt = (
            select(LaptopConfiguration)
            .options(
                selectinload(LaptopConfiguration.offers),
                selectinload(LaptopConfiguration.metrics),
            )
            .where(*filters)
            .order_by(
                LaptopConfiguration.min_price_egp.asc(),
                LaptopConfiguration.title.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().all(), total

    async def list_all_with_offers(self) -> Sequence[LaptopConfiguration]:
        """Fetch every configuration with eager-loaded offers for review dispatching."""
        stmt = (
            select(LaptopConfiguration)
            .options(selectinload(LaptopConfiguration.offers))
            .order_by(LaptopConfiguration.laptop_added_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    async def get_candidates_for_recommendation(
        self,
        max_budget_egp: float | None = None,
        brand_filter: list[str] | None = None,
    ) -> Sequence[LaptopConfiguration]:
        """Fetch active in-stock laptops with loaded offers and metrics for TOPSIS ranking."""
        stmt = (
            select(LaptopConfiguration)
            .options(
                selectinload(LaptopConfiguration.offers),
                selectinload(LaptopConfiguration.metrics),
            )
            .where(LaptopConfiguration.in_stock.is_(True))
            .where(LaptopConfiguration.min_price_egp > 0)
        )
        if max_budget_egp is not None:
            stmt = stmt.where(LaptopConfiguration.min_price_egp <= max_budget_egp)
        if brand_filter:
            lower_brands = [b.lower().strip() for b in brand_filter]
            stmt = stmt.where(func.lower(LaptopConfiguration.brand).in_(lower_brands))

        stmt = stmt.order_by(LaptopConfiguration.min_price_egp.asc())
        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    async def get_unreviewed_laptops(self) -> Sequence[LaptopConfiguration]:
        """Fetch laptop configurations that have not had community reviews collected.

        Offers are eagerly loaded so the caller can aggregate every store product
        URL for a chassis without triggering lazy-load I/O outside the session.
        """
        stmt = (
            select(LaptopConfiguration)
            .options(selectinload(LaptopConfiguration.offers))
            .where(LaptopConfiguration.has_reviews.is_(False))
            .order_by(LaptopConfiguration.laptop_added_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    async def mark_laptops_as_reviewed(
        self,
        laptop_ids: Sequence[uuid.UUID],
        timestamp: datetime | None = None,
    ) -> int:
        """Flag the given laptops as reviewed and stamp their review check time.

        Returns the number of rows matched by the bulk update.
        """
        ids = list(laptop_ids)
        if not ids:
            return 0

        stmt = (
            update(LaptopConfiguration)
            .where(LaptopConfiguration.id.in_(ids))
            .values(
                has_reviews=True,
                reviews_checked_at=timestamp or utcnow(),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount or 0

    async def update_review_intelligence_by_canonical_ids(
        self,
        results: Mapping[str, Any],
        timestamp: datetime | None = None,
    ) -> int:
        """Persist community review intelligence keyed by ``canonical_id``.

        Each value may be a mapping/DTO containing ``pros_en``, ``pros_ar``,
        ``cons_en``, ``cons_ar``, ``evidence_count``, ``community_nlp_score``
        and an ``aspect_scores`` mapping. The bilingual lists and evidence count
        live on ``LaptopConfiguration``; the NLP and aspect scores live on the
        associated ``LaptopMetrics`` row.

        Returns the number of catalog rows matched and updated.
        """
        if not results:
            return 0

        stmt = (
            select(LaptopConfiguration)
            .where(LaptopConfiguration.canonical_id.in_(list(results.keys())))
            .options(selectinload(LaptopConfiguration.metrics))
        )
        laptops = (await self.session.execute(stmt)).scalars().unique().all()

        reviewed_at = timestamp or utcnow()
        updated_count = 0

        for laptop in laptops:
            payload = _normalize_review_payload(results.get(laptop.canonical_id))
            if not payload:
                continue

            aspects = payload.get("aspect_scores")
            if not isinstance(aspects, Mapping):
                aspects = {}

            laptop.pros_en = _coerce_str_list(payload.get("pros_en"))
            laptop.pros_ar = _coerce_str_list(payload.get("pros_ar"))
            laptop.cons_en = _coerce_str_list(payload.get("cons_en"))
            laptop.cons_ar = _coerce_str_list(payload.get("cons_ar"))
            laptop.reviews_evidence_count = _coerce_optional_int(payload.get("evidence_count")) or 0
            laptop.has_reviews = True
            laptop.reviews_checked_at = reviewed_at

            metrics = laptop.metrics
            if metrics is not None:
                nlp_score = _coerce_optional_float(payload.get("community_nlp_score"))
                if nlp_score is not None:
                    metrics.community_nlp_score = nlp_score

                for key in _REVIEW_ASPECT_KEYS:
                    score = _coerce_optional_float(aspects.get(key, payload.get(key)))
                    if score is not None:
                        setattr(metrics, key, score)

            updated_count += 1

        await self.session.flush()
        return updated_count
