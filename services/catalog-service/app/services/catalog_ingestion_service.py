"""Catalog Ingestion Orchestration Service.

Wires the complete catalog pipeline:
1. Download catalog payload from Object Storage (S3) or local file.
2. In-memory metrics enrichment via CatalogMetricsService.
3. Placeholder hook for future TOPSIS persona modeling.
4. Relational database persistence via CatalogSeederRepository.
5. Store scraping watermark checkpoint updates via StoreScrapingPointerRepository.
6. Chassis-level community review dispatch via the transactional outbox.
7. Execution audit logging via BatchLogRepository.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import time
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.storage import IObjectStorageService, get_storage_service
from app.domain.reviews import ChassisTargetResolver, LaptopInputDto, ResolvedReviewTarget
from app.models.base import utcnow
from app.models.laptop import LaptopConfiguration
from app.repositories.batch_log_repository import BatchLogRepository
from app.repositories.laptop_repository import LaptopRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.pointer_repository import StoreScrapingPointerRepository
from app.repositories.seeder import CatalogSeederRepository, SeederSummary
from app.schemas.events import (
    EventType,
    LaptopReviewTarget,
    ScrapeReviewsCommand,
    ScrapeReviewsPayload,
)
from app.services.catalog_metrics_service import CatalogMetricsService

logger = logging.getLogger("catalog.services.ingestion")


@dataclass(frozen=True)
class IngestionResult:
    """Consolidated execution result for a catalog ingestion run."""

    batch_id: uuid.UUID
    status: str
    source: str
    duration_seconds: float
    total_laptops: int
    new_laptops: int
    updated_laptops: int
    offers_created: int
    offers_updated: int
    metrics_created: int
    metrics_updated: int
    metrics_summary: dict[str, Any]
    error_message: str | None = None


class CatalogIngestionService:
    """Orchestrates end-to-end catalog ingestion, enrichment, and relational persistence."""

    def __init__(
        self,
        storage_service: IObjectStorageService | None = None,
        metrics_service: CatalogMetricsService | None = None,
        review_resolver: ChassisTargetResolver | None = None,
    ) -> None:
        self.storage_service = storage_service or get_storage_service()
        self.metrics_service = metrics_service or CatalogMetricsService()
        self.review_resolver = review_resolver or ChassisTargetResolver()

    async def ingest_from_s3(
        self,
        session: AsyncSession,
        s3_key: str = "catalogs/unified_catalog_latest.json",
        trigger_type: str = "S3_INGESTION",
        batch_id: uuid.UUID | None = None,
    ) -> IngestionResult:
        """Download catalog from S3 and ingest into the catalog database."""
        logger.info("Starting catalog ingestion from S3 key: %s (bucket: %s)", s3_key, self.storage_service.bucket_name)
        source_label = f"s3://{self.storage_service.bucket_name}/{s3_key}"

        catalog_dict = self.storage_service.read_json(s3_key)
        return await self.ingest_catalog_dict(
            session=session,
            catalog_data=catalog_dict,
            source=source_label,
            trigger_type=trigger_type,
            batch_id=batch_id,
        )

    async def ingest_from_file(
        self,
        session: AsyncSession,
        file_path: Path,
        trigger_type: str = "FILE_SEEDER",
        batch_id: uuid.UUID | None = None,
    ) -> IngestionResult:
        """Load catalog from local filesystem and ingest into the catalog database."""
        logger.info("Starting catalog ingestion from local file: %s", file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Catalog file not found at: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            catalog_dict = json.load(f)

        return await self.ingest_catalog_dict(
            session=session,
            catalog_data=catalog_dict,
            source=str(file_path),
            trigger_type=trigger_type,
            batch_id=batch_id,
        )

    async def ingest_catalog_dict(
        self,
        session: AsyncSession,
        catalog_data: dict[str, Any],
        source: str,
        trigger_type: str = "INGESTION",
        batch_id: uuid.UUID | None = None,
    ) -> IngestionResult:
        """Run the end-to-end ingestion pipeline on a catalog dictionary."""
        start_time = time.perf_counter()
        bid = batch_id or uuid.uuid4()
        batch_repo = BatchLogRepository(session)
        pointer_repo = StoreScrapingPointerRepository(session)
        seeder_repo = CatalogSeederRepository(session)

        # 1. Initialize audit batch log (or update existing)
        existing_log = await batch_repo.get_by_id(bid)
        if existing_log:
            batch_log = existing_log
            batch_log.status = "STARTED"
        else:
            batch_log = await batch_repo.record_batch_log(
                batch_id=bid,
                store_key="catalog_ingestion",
                trigger_type=trigger_type,
                status="STARTED",
            )
        await session.flush()

        try:
            # 2. Enrich catalog with hardware performance metrics & topsis inputs
            logger.info("[%s] Running hardware metrics engine enrichment...", bid)
            enriched_data, metrics_summary = self.metrics_service.enrich_catalog_dict(catalog_data)

            # 3. Future TOPSIS persona recommender hook
            logger.info("[%s] Applying TOPSIS persona hook...", bid)
            ready_data = self.apply_topsis_personas(enriched_data)

            # 4. Relational database seeding via Seeder Repository
            logger.info("[%s] Seeding catalog into PostgreSQL...", bid)
            seeder_summary: SeederSummary = await seeder_repo.upsert_catalog(ready_data)

            # 5. Resolve unreviewed chassis and enqueue the review scrape command
            review_targets_queued = await self._dispatch_review_scrape_command(
                session=session,
                batch_id=bid,
            )

            # 6. Update store scraping watermark checkpoints
            await self._update_store_watermarks(pointer_repo, ready_data)

            elapsed = round(time.perf_counter() - start_time, 3)

            # 7. Finalize batch log
            batch_log.status = "SUCCESS"
            batch_log.completed_at = utcnow()
            batch_log.duration_seconds = elapsed
            batch_log.items_scraped = seeder_summary.total_laptops_processed
            batch_log.new_laptops_added = seeder_summary.new_laptops_created
            batch_log.offers_updated = seeder_summary.offers_updated
            await session.flush()

            logger.info(
                "[%s] Catalog ingestion successfully finished in %.3fs: %d processed (%d new, %d updated, "
                "%d chassis queued for reviews)",
                bid,
                elapsed,
                seeder_summary.total_laptops_processed,
                seeder_summary.new_laptops_created,
                seeder_summary.laptops_updated,
                review_targets_queued,
            )

            return IngestionResult(
                batch_id=bid,
                status="SUCCESS",
                source=source,
                duration_seconds=elapsed,
                total_laptops=seeder_summary.total_laptops_processed,
                new_laptops=seeder_summary.new_laptops_created,
                updated_laptops=seeder_summary.laptops_updated,
                offers_created=seeder_summary.offers_created,
                offers_updated=seeder_summary.offers_updated,
                metrics_created=seeder_summary.metrics_created,
                metrics_updated=seeder_summary.metrics_updated,
                metrics_summary=metrics_summary,
            )

        except Exception as exc:
            elapsed = round(time.perf_counter() - start_time, 3)
            logger.exception("[%s] Catalog ingestion failed after %.3fs: %s", bid, elapsed, exc)

            batch_log.status = "FAILED"
            batch_log.completed_at = utcnow()
            batch_log.duration_seconds = elapsed
            batch_log.error_message = str(exc)
            await session.flush()

            return IngestionResult(
                batch_id=bid,
                status="FAILED",
                source=source,
                duration_seconds=elapsed,
                total_laptops=0,
                new_laptops=0,
                updated_laptops=0,
                offers_created=0,
                offers_updated=0,
                metrics_created=0,
                metrics_updated=0,
                metrics_summary={},
                error_message=str(exc),
            )

    def apply_topsis_personas(self, catalog_data: dict[str, Any]) -> dict[str, Any]:
        """Placeholder hook for TOPSIS persona recommender engine.

        Will map laptops to personas once TOPSIS scoring logic is integrated.
        Currently passes through catalog unchanged.
        """
        return catalog_data

    async def _dispatch_review_scrape_command(
        self,
        session: AsyncSession,
        batch_id: uuid.UUID,
    ) -> int:
        """Resolve unreviewed chassis and enqueue one review scrape command.

        Stage 1 catalog ingestion only stages the ``reviews.scrape.command``
        outbox event inside the caller's seeding transaction. Newly discovered
        laptops intentionally remain ``has_reviews=False`` until Stage 2 review
        ingestion actually persists their NLP profile, at which point
        ``LaptopRepository.update_review_intelligence_by_canonical_ids`` stamps
        ``has_reviews=True`` and ``reviews_checked_at``.

        Returns:
            The number of chassis targets queued (0 when nothing to review).
        """
        laptop_repo = LaptopRepository(session)
        unreviewed = await laptop_repo.get_unreviewed_laptops()
        if not unreviewed:
            logger.info("[%s] No unreviewed laptops; skipping review scrape command.", batch_id)
            return 0

        inputs = [self._to_review_input(laptop) for laptop in unreviewed]
        targets = self.review_resolver.resolve(inputs)
        if not targets:
            logger.info("[%s] Chassis resolver produced no targets.", batch_id)
            return 0

        command = ScrapeReviewsCommand(
            correlation_id=str(batch_id),
            payload=ScrapeReviewsPayload(
                job_id=f"reviews_batch_{batch_id}",
                targets=[self._to_review_target(target) for target in targets],
            ),
        )

        await OutboxRepository(session).insert_outbox_event(
            event_type=EventType.REVIEWS_SCRAPE_COMMAND,
            routing_key=EventType.REVIEWS_SCRAPE_COMMAND,
            payload=command,
            correlation_id=str(batch_id),
        )

        logger.info(
            "[%s] Queued review scrape command: %d laptops collapsed into %d chassis targets.",
            batch_id,
            len(unreviewed),
            len(targets),
        )
        return len(targets)

    @staticmethod
    def _to_review_input(laptop: LaptopConfiguration) -> LaptopInputDto:
        """Project a LaptopConfiguration ORM row into a pure domain DTO."""
        offers = list(laptop.offers or [])
        product_urls = tuple(
            dict.fromkeys(
                offer.product_url.strip() for offer in offers if offer.product_url and offer.product_url.strip()
            )
        )
        retailer_skus = tuple(
            dict.fromkeys(
                offer.retailer_sku.strip() for offer in offers if offer.retailer_sku and offer.retailer_sku.strip()
            )
        )
        return LaptopInputDto(
            laptop_id=str(laptop.id),
            canonical_id=laptop.canonical_id,
            title=laptop.title,
            brand=laptop.brand,
            laptop_family=laptop.laptop_family,
            laptop_model=laptop.laptop_model,
            mpn=laptop.mpn,
            thumbnail_url=laptop.thumbnail_url,
            screen_size=float(laptop.display_size_inches) if laptop.display_size_inches is not None else None,
            retailer_skus=retailer_skus,
            product_urls=product_urls,
        )

    @staticmethod
    def _to_review_target(target: ResolvedReviewTarget) -> LaptopReviewTarget:
        """Map a pure resolved chassis target onto the transport event schema."""
        return LaptopReviewTarget(
            laptop_id=target.laptop_id,
            canonical_id=target.canonical_id,
            chassis_key=getattr(target, "chassis_key", None),
            title=target.title,
            brand=target.brand,
            laptop_family=target.laptop_family,
            laptop_model=target.laptop_model,
            mpn=target.mpn,
            manufacturer_part_number=target.manufacturer_part_number,
            retailer_sku=target.retailer_sku,
            skus=list(target.skus),
            mpns=list(target.mpns),
            product_urls=list(target.product_urls),
            thumbnail_url=target.thumbnail_url,
            screen_size=target.screen_size,
            matched_laptop_ids=list(target.matched_laptop_ids),
            matched_canonical_ids=list(target.matched_canonical_ids),
        )

    async def _update_store_watermarks(
        self,
        pointer_repo: StoreScrapingPointerRepository,
        catalog_data: dict[str, Any],
    ) -> None:
        """Extract store watermarks and update checkpoints in store_scraping_pointer."""
        laptops = catalog_data.get("laptops", [])
        store_offers_count: dict[str, int] = {}
        store_domains: dict[str, str] = {}
        store_names: dict[str, str] = {}
        store_latest_models: dict[str, list[str]] = {}

        for laptop in laptops:
            for offer in laptop.get("offers", []):
                skey = str(offer.get("store_key") or "generic").lower().strip()
                sname = str(offer.get("store_name") or skey)
                sdomain = offer.get("store_domain")
                is_active = offer.get("in_stock", True) and offer.get("is_valid_price", True)

                if is_active:
                    store_offers_count[skey] = store_offers_count.get(skey, 0) + 1
                if sdomain:
                    store_domains[skey] = str(sdomain)
                if sname:
                    store_names[skey] = sname

                sku_or_mpn = offer.get("retailer_sku") or offer.get("mpn") or laptop.get("canonical_id")
                if sku_or_mpn:
                    if skey not in store_latest_models:
                        store_latest_models[skey] = []
                    if len(store_latest_models[skey]) < 10 and sku_or_mpn not in store_latest_models[skey]:
                        store_latest_models[skey].append(str(sku_or_mpn))

        now = utcnow()
        for skey, count in store_offers_count.items():
            await pointer_repo.upsert_pointer(
                store_key=skey,
                store_name=store_names.get(skey, skey),
                store_domain=store_domains.get(skey),
                total_active_offers=count,
                latest_pointers=store_latest_models.get(skey, []),
                last_scraped_at=now,
            )
