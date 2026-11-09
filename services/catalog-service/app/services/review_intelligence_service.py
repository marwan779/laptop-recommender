"""Stage 2 review intelligence orchestration service.

Coordinates the two halves of the community-review pipeline:

1. Chassis dispatch - resolve catalog laptops into physical chassis targets and
   enqueue a ``reviews.scrape.command`` through the transactional outbox.
2. Review ingestion - embed enriched pro/con/context documents into ChromaDB
   and persist the bilingual NLP profile, aspect scores, evidence count, and
   reviewed flags into PostgreSQL via repositories.

Clean Architecture note: this module contains orchestration only. All SQL lives
in repositories and all ChromaDB access lives in ``ChromaReviewsService``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import time
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.review_text import align_bilingual_lists
from app.common.storage import IObjectStorageService, get_storage_service
from app.domain.reviews import ChassisTargetResolver, LaptopInputDto, ResolvedReviewTarget
from app.models.laptop import LaptopConfiguration
from app.repositories.laptop_repository import LaptopRepository
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.events import (
    EventType,
    LaptopReviewTarget,
    ScrapeReviewsCommand,
    ScrapeReviewsPayload,
)
from app.schemas.scraping import ReviewsTriggerResponse
from app.services.chroma_reviews_service import (
    ChromaReviewsService,
    get_chroma_reviews_service,
)

logger = logging.getLogger("catalog.services.review_intelligence")

DEFAULT_REVIEWS_S3_KEY = "reviews/cleaned_and_enriched_chassis_reviews_v6.json"


@dataclass(frozen=True)
class ReviewIngestionResult:
    """Execution summary for a review intelligence ingestion run."""

    status: str
    chassis_processed: int
    chroma_documents_upserted: int
    sql_laptops_updated: int
    duration_seconds: float


class ReviewIntelligenceService:
    """Application service orchestrating Stage 2 review dispatch and ingestion."""

    def __init__(
        self,
        storage_service: IObjectStorageService | None = None,
        chroma_service: ChromaReviewsService | None = None,
        review_resolver: ChassisTargetResolver | None = None,
    ) -> None:
        self._storage_service = storage_service
        self.chroma_service = chroma_service or get_chroma_reviews_service()
        self.review_resolver = review_resolver or ChassisTargetResolver()

    @property
    def storage_service(self) -> IObjectStorageService:
        if self._storage_service is None:
            self._storage_service = get_storage_service()
        return self._storage_service

    # ─── Dispatch ───────────────────────────────────────────────────────────

    async def dispatch_review_scraping(
        self,
        session: AsyncSession,
        force_all: bool = False,
    ) -> ReviewsTriggerResponse:
        """Resolve unreviewed (or all) laptops into chassis targets and enqueue scraping."""
        laptop_repo = LaptopRepository(session)
        laptops = (
            await laptop_repo.list_all_with_offers()
            if force_all
            else await laptop_repo.get_unreviewed_laptops()
        )

        job_id = f"reviews_{uuid.uuid4().hex[:12]}"
        if not laptops:
            return ReviewsTriggerResponse(
                job_id=job_id,
                status="NO_UNREVIEWED_LAPTOPS",
                chassis_targets_queued=0,
                laptops_matched=0,
                message="No laptops require community review collection.",
            )

        inputs = [self._to_review_input(laptop) for laptop in laptops]
        targets = self.review_resolver.resolve(inputs)
        if not targets:
            return ReviewsTriggerResponse(
                job_id=job_id,
                status="NO_TARGETS",
                chassis_targets_queued=0,
                laptops_matched=len(laptops),
                message="Chassis resolution produced no review targets.",
            )

        command = ScrapeReviewsCommand(
            correlation_id=job_id,
            payload=ScrapeReviewsPayload(
                job_id=job_id,
                targets=[self._to_review_target(target) for target in targets],
            ),
        )
        await OutboxRepository(session).insert_outbox_event(
            event_type=EventType.REVIEWS_SCRAPE_COMMAND,
            routing_key=EventType.REVIEWS_SCRAPE_COMMAND,
            payload=command,
            correlation_id=job_id,
        )
        await session.commit()

        logger.info(
            "Queued review scrape command [%s]: %d laptops collapsed into %d chassis targets.",
            job_id,
            len(laptops),
            len(targets),
        )
        return ReviewsTriggerResponse(
            job_id=job_id,
            status="QUEUED",
            chassis_targets_queued=len(targets),
            laptops_matched=len(laptops),
            message=(
                f"Queued {len(targets)} chassis targets from {len(laptops)} laptops "
                "for community review scraping."
            ),
        )

    # ─── Ingestion ──────────────────────────────────────────────────────────

    async def ingest_from_file(
        self,
        session: AsyncSession,
        source_path: str | Path | None = None,
    ) -> ReviewIngestionResult:
        """Load an enriched reviews artifact from disk and ingest it."""
        path = Path(source_path) if source_path else self.chroma_service.reviews_json_path
        if not path.exists():
            raise FileNotFoundError(f"Reviews artifact not found at: {path}")

        data = await asyncio.to_thread(self._read_json_file, path)
        return await self.ingest_reviews_dict(session, data)

    async def ingest_from_s3(
        self,
        session: AsyncSession,
        s3_key: str | None = None,
    ) -> ReviewIngestionResult:
        """Load an enriched reviews artifact from object storage and ingest it."""
        key = s3_key or DEFAULT_REVIEWS_S3_KEY
        data = await asyncio.to_thread(self.storage_service.read_json, key)
        return await self.ingest_reviews_dict(session, data)

    async def ingest_reviews_dict(
        self,
        session: AsyncSession,
        reviews_data: dict[str, Any],
    ) -> ReviewIngestionResult:
        """Embed chassis reviews into ChromaDB and persist NLP profiles to PostgreSQL."""
        start_time = time.perf_counter()
        laptops = [
            item
            for item in (reviews_data.get("laptops") or [])
            if isinstance(item, dict)
        ]
        profiles = self._collect_review_profiles(laptops)

        if not profiles:
            return ReviewIngestionResult(
                status="SKIPPED",
                chassis_processed=len(laptops),
                chroma_documents_upserted=0,
                sql_laptops_updated=0,
                duration_seconds=round(time.perf_counter() - start_time, 3),
            )

        chroma_documents = await asyncio.to_thread(
            self.chroma_service.upsert_chassis_reviews,
            laptops,
        )

        sql_updated = await LaptopRepository(
            session
        ).update_review_intelligence_by_canonical_ids(profiles)
        await session.commit()

        elapsed = round(time.perf_counter() - start_time, 3)
        logger.info(
            "Review intelligence ingested: %d chassis, %d Chroma documents, %d SQL laptops in %.3fs.",
            len(laptops),
            chroma_documents,
            sql_updated,
            elapsed,
        )
        return ReviewIngestionResult(
            status="SUCCESS",
            chassis_processed=len(laptops),
            chroma_documents_upserted=chroma_documents,
            sql_laptops_updated=sql_updated,
            duration_seconds=elapsed,
        )

    # ─── Mappers ────────────────────────────────────────────────────────────

    @staticmethod
    def _collect_review_profiles(
        laptops: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Map every matched canonical id to its chassis NLP review profile."""
        profiles: dict[str, dict[str, Any]] = {}

        for item in laptops:
            profile = item.get("nlp_review_profile") or {}
            if not isinstance(profile, dict) or not profile:
                continue

            clean_profile = dict(profile)
            p_en, p_ar = align_bilingual_lists(profile.get("pros_en"), profile.get("pros_ar"))
            c_en, c_ar = align_bilingual_lists(profile.get("cons_en"), profile.get("cons_ar"))
            clean_profile["pros_en"] = p_en
            clean_profile["pros_ar"] = p_ar
            clean_profile["cons_en"] = c_en
            clean_profile["cons_ar"] = c_ar

            canonical_ids = list(item.get("matched_canonical_ids") or [])
            primary_canonical_id = item.get("primary_canonical_id")
            if primary_canonical_id and primary_canonical_id not in canonical_ids:
                canonical_ids.append(primary_canonical_id)

            for canonical_id in canonical_ids:
                if canonical_id:
                    profiles[str(canonical_id)] = clean_profile

        return profiles

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _to_review_input(laptop: LaptopConfiguration) -> LaptopInputDto:
        offers = list(laptop.offers or [])
        product_urls = tuple(
            dict.fromkeys(
                offer.product_url.strip()
                for offer in offers
                if offer.product_url and offer.product_url.strip()
            )
        )
        retailer_skus = tuple(
            dict.fromkeys(
                offer.retailer_sku.strip()
                for offer in offers
                if offer.retailer_sku and offer.retailer_sku.strip()
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
            screen_size=(
                float(laptop.display_size_inches)
                if laptop.display_size_inches is not None
                else None
            ),
            retailer_skus=retailer_skus,
            product_urls=product_urls,
        )

    @staticmethod
    def _to_review_target(target: ResolvedReviewTarget) -> LaptopReviewTarget:
        return LaptopReviewTarget(
            laptop_id=target.laptop_id,
            canonical_id=target.canonical_id,
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


__all__ = ["ReviewIngestionResult", "ReviewIntelligenceService"]
