import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache.provider import ICacheProvider
from app.domain.pricing import (
    OfferSnapshot,
    PriceChangeType,
    PricingDomainService,
)
from app.models.base import utcnow
from app.models.metrics import LaptopMetrics
from app.models.offer import LaptopOffer
from app.repositories.batch_log_repository import BatchLogRepository
from app.repositories.laptop_repository import LaptopRepository
from app.repositories.offer_repository import OfferRepository
from app.repositories.price_history_repository import PriceHistoryRepository
from app.schemas.price_sync import (
    PriceCheckBatchRequest,
    PriceCheckBatchResponse,
    PriceCheckItem,
    PriceSyncSummary,
)

logger = logging.getLogger(__name__)


class PriceSyncService:
    """Application use case managing the lifecycle of price monitoring.

    Orchestrates between repository persistence and pure domain pricing rules:
    1. Generates store-partitioned batch requests via OfferRepository.
    2. Applies live scraper diffs, delegating business rules and math to PricingDomainService.
    3. Appends price-history observations and persists rollups, metrics, and audit logs.
    """

    def __init__(
        self,
        domain_service: type[PricingDomainService] = PricingDomainService,
        cache: ICacheProvider | None = None,
    ):
        self.domain = domain_service
        self.cache = cache

    async def build_price_check_batches(
        self,
        session: AsyncSession,
        store_key: str | None = None,
        limit: int = 50,
    ) -> list[PriceCheckBatchRequest]:
        """Query stale offers via repository, partition by store, and build batch requests."""
        offer_repo = OfferRepository(session)
        offers = await offer_repo.get_stale_offers(store_key=store_key, limit=limit)

        # Partition offers by store_key
        grouped: dict[str, list[LaptopOffer]] = {}
        for o in offers:
            grouped.setdefault(o.store_key, []).append(o)

        batches: list[PriceCheckBatchRequest] = []
        for s_key, s_offers in grouped.items():
            items = [
                PriceCheckItem(
                    offer_id=str(o.id),
                    laptop_id=str(o.laptop_configuration_id),
                    product_url=o.product_url,
                    current_price_egp=float(o.price_egp),
                    current_in_stock=bool(o.in_stock),
                )
                for o in s_offers
            ]
            batch = PriceCheckBatchRequest(
                batch_id=str(uuid.uuid4()),
                store_key=s_key,
                store_name=s_offers[0].store_name if s_offers else s_key.capitalize(),
                items=items,
            )
            batches.append(batch)

        return batches

    async def apply_batch_results(
        self,
        session: AsyncSession,
        batch_response: PriceCheckBatchResponse | dict,
        commit: bool = True,
    ) -> PriceSyncSummary:
        """Process price monitor response, update offers, roll up parent laptops,

        and recalibrate price-dependent hardware value metrics using pure domain rules.

        ``commit=False`` leaves the transaction open so a caller (e.g. a CLI
        runner performing a dry run) can decide whether to commit or roll back.
        """
        if isinstance(batch_response, dict):
            resp = PriceCheckBatchResponse(**batch_response)
        else:
            resp = batch_response

        offer_repo = OfferRepository(session)
        laptop_repo = LaptopRepository(session)
        log_repo = BatchLogRepository(session)
        history_repo = PriceHistoryRepository(session)

        affected_laptop_ids: set[uuid.UUID] = set()
        unchanged_offer_ids: list[uuid.UUID] = []

        summary = PriceSyncSummary(
            batch_id=resp.batch_id,
            store_key=resp.store_key,
            total_processed=len(resp.results),
        )

        # 1. Update individual store offers using pure domain evaluation
        for r in resp.results:
            try:
                offer_uuid = uuid.UUID(r.offer_id)
            except (ValueError, TypeError):
                continue

            if not r.has_changed and not r.error_message:
                unchanged_offer_ids.append(offer_uuid)
                summary.offers_unchanged += 1
                continue

            if r.has_changed:
                offer = await offer_repo.get_by_id(offer_uuid)
                if not offer:
                    continue

                # Delegate evaluation to pure domain policy
                transition = self.domain.evaluate_offer_transition(
                    current_price=float(offer.price_egp),
                    new_price=r.new_price_egp,
                    current_stock=bool(offer.in_stock),
                    new_stock=r.new_in_stock,
                )

                if transition.has_changed:
                    if transition.is_price_drop or transition.is_price_hike:
                        offer.previous_price_egp = offer.price_egp
                        offer.price_egp = transition.new_price
                        offer.price_updated_at = utcnow()

                    offer.in_stock = transition.new_in_stock
                    offer.last_checked_at = utcnow()

                    # Append the event-log observation inside the same transaction.
                    if transition.new_price is not None and float(transition.new_price) > 0:
                        await history_repo.record_point(
                            offer_id=offer.id,
                            laptop_configuration_id=offer.laptop_configuration_id,
                            store_key=(offer.store_key or "generic").lower().strip(),
                            price_egp=float(transition.new_price),
                            in_stock=transition.new_in_stock,
                            recorded_at=offer.last_checked_at,
                        )

                    summary.offers_updated += 1
                    if transition.change_type == PriceChangeType.PRICE_DROP:
                        summary.price_drops_detected += 1
                    elif transition.change_type == PriceChangeType.PRICE_HIKE:
                        summary.price_hikes_detected += 1
                    elif transition.change_type == PriceChangeType.OUT_OF_STOCK:
                        summary.out_of_stock_detected += 1

                    affected_laptop_ids.add(offer.laptop_configuration_id)
                else:
                    unchanged_offer_ids.append(offer_uuid)
                    summary.offers_unchanged += 1

        # Fast repository bulk update for unchanged offers freshness watermark
        if unchanged_offer_ids:
            await offer_repo.bulk_touch_watermarks(unchanged_offer_ids)

        # 2. Recompute rollup aggregations on parent LaptopConfiguration
        for laptop_id in affected_laptop_ids:
            laptop = await laptop_repo.get_by_id(laptop_id)
            if not laptop:
                continue

            # Query all active offers for this laptop via repository
            all_offers = await offer_repo.get_offers_by_laptop_id(laptop_id)
            if not all_offers:
                continue

            # Convert to pure domain snapshots
            snapshots = [
                OfferSnapshot(
                    store_key=o.store_key,
                    price_egp=float(o.price_egp),
                    in_stock=bool(o.in_stock),
                    is_valid_price=bool(o.is_valid_price),
                )
                for o in all_offers
            ]

            # Calculate rollups through pure domain service
            rollup = self.domain.calculate_laptop_rollup(snapshots)
            if not rollup:
                continue

            # Price drop detection on canonical model level
            if rollup.min_price_egp < float(laptop.min_price_egp):
                laptop.previous_min_price_egp = laptop.min_price_egp
                laptop.price_updated_at = utcnow()

            laptop.min_price_egp = rollup.min_price_egp
            laptop.max_price_egp = rollup.max_price_egp
            laptop.cheapest_store = rollup.cheapest_store
            laptop.price_spread_egp = rollup.price_spread_egp
            laptop.in_stock = rollup.in_stock
            laptop.price_checked_at = utcnow()

            summary.parent_laptops_recalculated += 1

            # 3. Recalibrate LaptopMetrics using pure domain mathematics
            metrics = await session.get(LaptopMetrics, laptop_id)
            if metrics:
                metrics_recalc = self.domain.recalculate_value_score(
                    min_price_egp=rollup.min_price_egp,
                    cpu_score=float(metrics.cpu_score),
                    gpu_score=float(metrics.gpu_score),
                    display_score=float(metrics.display_score),
                    longevity_score=float(metrics.longevity_score),
                    ram_capacity_gb=float(laptop.ram_capacity_gb or 16),
                )

                metrics.effective_price_egp = metrics_recalc.effective_price_egp
                metrics.in_stock_active = rollup.in_stock
                metrics.value_score = metrics_recalc.value_score
                metrics.pricing_status = metrics_recalc.pricing_status
                metrics.updated_at = utcnow()

                summary.metrics_recalibrated += 1

        # 4. Insert execution audit log via BatchLogRepository
        try:
            batch_uuid = uuid.UUID(resp.batch_id)
        except (ValueError, TypeError):
            batch_uuid = uuid.uuid4()

        await log_repo.record_batch_log(
            batch_id=batch_uuid,
            store_key=resp.store_key,
            trigger_type="PRICE_MONITOR",
            status="SUCCESS" if resp.errors_count == 0 else "PARTIAL",
            duration_seconds=resp.duration_seconds,
            items_scraped=resp.total_items,
            offers_updated=summary.offers_updated,
        )

        if commit:
            await session.commit()

            # Evict cached price-history payloads for every affected canonical laptop.
            await self._invalidate_price_history_cache(session, affected_laptop_ids)

        return summary

    async def _invalidate_price_history_cache(
        self,
        session: AsyncSession,
        laptop_ids: set[uuid.UUID],
    ) -> None:
        """Clear cached price-history curves and catalog responses for laptops touched by this batch."""
        if not self.cache or not laptop_ids:
            return

        prefixes = [
            "catalog:price_history",
            "catalog:laptop",
            "catalog:browse",
            "catalog:recommendation",
        ]
        laptop_repo = LaptopRepository(session)
        for laptop_id in laptop_ids:
            prefixes.append(f"catalog:price_history:{laptop_id}")
            laptop = await laptop_repo.get_by_id(laptop_id)
            if laptop and laptop.canonical_id:
                prefixes.append(f"catalog:price_history:{laptop.canonical_id}")

        for prefix in prefixes:
            try:
                await self.cache.clear_prefix(prefix)
            except Exception as exc:
                logger.warning(
                    "Failed to invalidate cache for '%s': %s",
                    prefix,
                    exc,
                )
