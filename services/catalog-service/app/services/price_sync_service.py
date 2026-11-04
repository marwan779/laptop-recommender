import logging
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.laptop import LaptopConfiguration
from app.models.metrics import LaptopMetrics
from app.models.offer import LaptopOffer
from app.models.scraping import ScrapingBatchLog
from app.schemas.price_sync import (
    PriceChangeType,
    PriceCheckBatchRequest,
    PriceCheckBatchResponse,
    PriceCheckItem,
    PriceSyncSummary,
)

logger = logging.getLogger(__name__)


class PriceSyncService:
    """Manages the catalog-side lifecycle of store price monitoring.

    Generates partitioned batch requests for scraper-service and handles
    ingestion, rollup pricing aggregations, and metric recalibrations.
    """

    async def build_price_check_batches(
        self,
        session: AsyncSession,
        store_key: str | None = None,
        limit: int = 50,
    ) -> list[PriceCheckBatchRequest]:
        """Query stale offers from PostgreSQL, partition by store, and build batch requests."""
        stmt = (
            select(LaptopOffer)
            .where(LaptopOffer.is_valid_price.is_(True))
            .order_by(LaptopOffer.last_checked_at.asc().nullsfirst())
        )
        if store_key:
            stmt = stmt.where(LaptopOffer.store_key == store_key.lower().strip())
        if limit:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        offers = result.scalars().all()

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
    ) -> PriceSyncSummary:
        """Process price monitor response, update offers, roll up parent laptops,

        and recalibrate price-dependent hardware value metrics.
        """
        if isinstance(batch_response, dict):
            resp = PriceCheckBatchResponse(**batch_response)
        else:
            resp = batch_response

        affected_laptop_ids: set[uuid.UUID] = set()
        unchanged_offer_ids: list[uuid.UUID] = []

        summary = PriceSyncSummary(
            batch_id=resp.batch_id,
            store_key=resp.store_key,
            total_processed=len(resp.results),
        )

        # 1. Update individual store offers
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
                offer = await session.get(LaptopOffer, offer_uuid)
                if not offer:
                    continue

                if r.new_price_egp is not None and abs(float(r.new_price_egp) - float(offer.price_egp)) >= 1.0:
                    offer.previous_price_egp = offer.price_egp
                    offer.price_egp = r.new_price_egp
                    offer.price_updated_at = utcnow()

                offer.in_stock = r.new_in_stock
                offer.last_checked_at = utcnow()

                summary.offers_updated += 1
                if r.change_type == PriceChangeType.PRICE_DROP:
                    summary.price_drops_detected += 1
                elif r.change_type == PriceChangeType.PRICE_HIKE:
                    summary.price_hikes_detected += 1
                elif r.change_type == PriceChangeType.OUT_OF_STOCK:
                    summary.out_of_stock_detected += 1

                affected_laptop_ids.add(offer.laptop_configuration_id)

        # Fast bulk update for unchanged offers freshness watermark
        if unchanged_offer_ids:
            await session.execute(
                update(LaptopOffer).where(LaptopOffer.id.in_(unchanged_offer_ids)).values(last_checked_at=utcnow())
            )

        # 2. Recompute rollup aggregations on parent LaptopConfiguration
        for laptop_id in affected_laptop_ids:
            laptop = await session.get(LaptopConfiguration, laptop_id)
            if not laptop:
                continue

            # Query all active offers for this laptop
            stmt = select(LaptopOffer).where(LaptopOffer.laptop_configuration_id == laptop_id)
            all_offers = (await session.execute(stmt)).scalars().all()
            if not all_offers:
                continue

            active_in_stock = [
                o for o in all_offers if o.in_stock and o.is_valid_price and float(o.price_egp) >= 5000.0
            ]

            if active_in_stock:
                cheapest_offer = min(active_in_stock, key=lambda o: float(o.price_egp))
                new_min = float(cheapest_offer.price_egp)
                new_max = max(float(o.price_egp) for o in active_in_stock)
                cheapest_store = cheapest_offer.store_key
                is_in_stock = True
            else:
                cheapest_offer = min(all_offers, key=lambda o: float(o.price_egp))
                new_min = float(cheapest_offer.price_egp)
                new_max = max(float(o.price_egp) for o in all_offers)
                cheapest_store = cheapest_offer.store_key
                is_in_stock = False

            # Price drop detection on canonical model level
            if new_min < float(laptop.min_price_egp):
                laptop.previous_min_price_egp = laptop.min_price_egp
                laptop.price_updated_at = utcnow()

            laptop.min_price_egp = new_min
            laptop.max_price_egp = new_max
            laptop.cheapest_store = cheapest_store
            laptop.price_spread_egp = round(new_max - new_min, 2)
            laptop.in_stock = is_in_stock
            laptop.price_checked_at = utcnow()

            summary.parent_laptops_recalculated += 1

            # 3. Recalibrate LaptopMetrics (value_score & effective_price_egp)
            metrics = await session.get(LaptopMetrics, laptop_id)
            if metrics:
                metrics.effective_price_egp = new_min
                metrics.in_stock_active = is_in_stock

                # Recalculate Composite Hardware Capability and Value Ratio
                ram_cap = float(laptop.ram_capacity_gb or 16)
                ram_pts = ram_cap / 32.0 * 100.0 if ram_cap <= 32.0 else 100.0
                composite_hw = (
                    0.28 * float(metrics.cpu_score)
                    + 0.32 * float(metrics.gpu_score)
                    + 0.15 * float(metrics.display_score)
                    + 0.10 * ram_pts
                    + 0.15 * float(metrics.longevity_score)
                )

                if new_min >= 10000.0:
                    val_ratio = round((composite_hw**1.35) / (new_min / 10000.0), 2)
                    raw_val_score = (val_ratio - 18.0) / (58.0 - 18.0) * 100.0
                    metrics.value_score = round(max(15.0, min(100.0, raw_val_score)), 2)

                metrics.updated_at = utcnow()
                summary.metrics_recalibrated += 1

        # 4. Insert execution log into scraping_batch_log
        try:
            batch_uuid = uuid.UUID(resp.batch_id)
        except (ValueError, TypeError):
            batch_uuid = uuid.uuid4()

        batch_log = ScrapingBatchLog(
            id=batch_uuid,
            store_key=resp.store_key,
            trigger_type="PRICE_MONITOR",
            status="SUCCESS" if resp.errors_count == 0 else "PARTIAL",
            duration_seconds=resp.duration_seconds,
            items_scraped=resp.total_items,
            offers_updated=summary.offers_updated,
        )
        session.add(batch_log)

        await session.commit()
        return summary
