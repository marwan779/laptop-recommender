"""Stage 2 review intelligence orchestration service.

Coordinates the two halves of the community-review pipeline:

1. Chassis dispatch - resolve catalog laptops into physical chassis targets and
   enqueue a ``reviews.scrape.command`` through the transactional outbox.
2. Review ingestion - persist the enriched bilingual NLP profile, aspect scores,
   evidence count, and reviewed flags into PostgreSQL via repositories.

Clean Architecture note: this module contains orchestration only; all SQL lives
in repositories.
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
from app.services.review_target_mapper import to_review_input, to_review_target

logger = logging.getLogger("catalog.services.review_intelligence")

DEFAULT_REVIEWS_S3_KEY = "reviews/cleaned_and_enriched_chassis_reviews_v6.json"


@dataclass(frozen=True)
class ReviewIngestionResult:
    """Execution summary for a review intelligence ingestion run."""

    status: str
    chassis_processed: int
    chroma_documents_upserted: int = 0
    sql_laptops_updated: int = 0
    duration_seconds: float = 0.0


class ReviewIntelligenceService:
    """Application service orchestrating Stage 2 review dispatch and ingestion."""

    DEFAULT_REVIEWS_JSON_PATH = (
        Path(__file__).resolve().parent.parent.parent / "data" / "cleaned_and_enriched_chassis_reviews_v6.json"
    )

    def __init__(
        self,
        storage_service: IObjectStorageService | None = None,
        review_resolver: ChassisTargetResolver | None = None,
        reviews_json_path: Path | None = None,
    ) -> None:
        self._storage_service = storage_service
        self.review_resolver = review_resolver or ChassisTargetResolver()
        self.reviews_json_path = reviews_json_path or self.DEFAULT_REVIEWS_JSON_PATH

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
        *,
        limit: int | None = None,
        upload_to_s3: bool = True,
        commit: bool = True,
    ) -> ReviewsTriggerResponse:
        """Resolve unreviewed (or all) laptops into chassis targets and enqueue scraping."""
        laptop_repo = LaptopRepository(session)
        laptops = await laptop_repo.list_all_with_offers() if force_all else await laptop_repo.get_unreviewed_laptops()

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

        if limit is not None and limit > 0:
            targets = targets[:limit]

        matched_laptop_count = sum(len(t.matched_laptop_ids) or 1 for t in targets)

        command = ScrapeReviewsCommand(
            correlation_id=job_id,
            payload=ScrapeReviewsPayload(
                job_id=job_id,
                targets=[self._to_review_target(target) for target in targets],
                upload_to_s3=upload_to_s3,
            ),
        )
        await OutboxRepository(session).insert_outbox_event(
            event_type=EventType.REVIEWS_SCRAPE_COMMAND,
            routing_key=EventType.REVIEWS_SCRAPE_COMMAND,
            payload=command,
            correlation_id=job_id,
        )
        if commit:
            await session.commit()
        else:
            await session.flush()

        logger.info(
            "Queued review scrape command [%s]: %d laptops collapsed into %d chassis targets (upload_to_s3=%s).",
            job_id,
            matched_laptop_count,
            len(targets),
            upload_to_s3,
        )
        return ReviewsTriggerResponse(
            job_id=job_id,
            status="QUEUED",
            chassis_targets_queued=len(targets),
            laptops_matched=matched_laptop_count,
            message=(
                f"Queued {len(targets)} chassis targets from {matched_laptop_count} laptops for community review scraping."
            ),
        )

    # ─── Ingestion ──────────────────────────────────────────────────────────

    async def ingest_from_file(
        self,
        session: AsyncSession,
        source_path: str | Path | None = None,
        commit: bool = True,
    ) -> ReviewIngestionResult:
        """Load an enriched reviews artifact from disk and ingest it."""
        path = Path(source_path) if source_path else self.reviews_json_path
        if not path.exists():
            raise FileNotFoundError(f"Reviews artifact not found at: {path}")

        data = await asyncio.to_thread(self._read_json_file, path)
        return await self.ingest_reviews_dict(session, data, commit=commit)

    async def ingest_from_s3(
        self,
        session: AsyncSession,
        s3_key: str | None = None,
        commit: bool = True,
    ) -> ReviewIngestionResult:
        """Load an enriched reviews artifact from object storage and ingest it."""
        key = s3_key or DEFAULT_REVIEWS_S3_KEY
        data = await asyncio.to_thread(self.storage_service.read_json, key)
        return await self.ingest_reviews_dict(session, data, commit=commit)

    async def ingest_reviews_dict(
        self,
        session: AsyncSession,
        reviews_data: dict[str, Any],
        commit: bool = True,
    ) -> ReviewIngestionResult:
        """Persist enriched community NLP profiles to PostgreSQL."""
        start_time = time.perf_counter()
        raw_items = reviews_data.get("chassis_reviews")
        if not isinstance(raw_items, list) or not raw_items:
            raw_items = reviews_data.get("laptops") or []
        chassis_items = [item for item in raw_items if isinstance(item, dict)]
        profiles = self._collect_review_profiles(chassis_items)

        if not profiles:
            return ReviewIngestionResult(
                status="SKIPPED",
                chassis_processed=len(chassis_items),
                chroma_documents_upserted=0,
                sql_laptops_updated=0,
                duration_seconds=round(time.perf_counter() - start_time, 3),
            )

        sql_updated = await LaptopRepository(session).update_review_intelligence_by_canonical_ids(profiles)
        if commit:
            await session.commit()

        elapsed = round(time.perf_counter() - start_time, 3)
        logger.info(
            "Review intelligence ingested: %d chassis, %d SQL laptops in %.3fs.",
            len(chassis_items),
            sql_updated,
            elapsed,
        )
        return ReviewIngestionResult(
            status="SUCCESS",
            chassis_processed=len(chassis_items),
            chroma_documents_upserted=0,
            sql_laptops_updated=sql_updated,
            duration_seconds=elapsed,
        )

    # ─── Mappers ────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_profile_dict(item: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize Format B1 (`nlp_review_profile`) or Format B2 (`chassis_reviews`) into one profile."""
        profile = item.get("nlp_review_profile")
        if isinstance(profile, dict) and profile:
            return dict(profile)

        lists = item.get("clean_profile_lists") if isinstance(item.get("clean_profile_lists"), dict) else {}
        aspects = item.get("aspect_scores")
        nlp_score = item.get("community_nlp_score")
        has_bilingual = any(item.get(k) for k in ("pros_en", "pros_ar", "cons_en", "cons_ar"))
        if not lists and not isinstance(aspects, dict) and nlp_score is None and not has_bilingual:
            return None

        chunks = item.get("deduplicated_chunks") or []
        evidence_count = item.get("evidence_count")
        if evidence_count is None:
            evidence_count = len(chunks) if isinstance(chunks, list) else 0

        return {
            "pros_en": lists.get("pros_en") if lists else item.get("pros_en"),
            "pros_ar": lists.get("pros_ar") if lists else item.get("pros_ar"),
            "cons_en": lists.get("cons_en") if lists else item.get("cons_en"),
            "cons_ar": lists.get("cons_ar") if lists else item.get("cons_ar"),
            "aspect_scores": aspects if isinstance(aspects, dict) else {},
            "community_nlp_score": nlp_score,
            "evidence_count": evidence_count,
        }

    @classmethod
    def _collect_review_profiles(
        cls,
        laptops: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Map every matched canonical id to its chassis NLP review profile."""
        profiles: dict[str, dict[str, Any]] = {}

        for item in laptops:
            clean_profile = cls._extract_profile_dict(item)
            if not clean_profile:
                continue

            p_en, p_ar = align_bilingual_lists(clean_profile.get("pros_en"), clean_profile.get("pros_ar"))
            c_en, c_ar = align_bilingual_lists(clean_profile.get("cons_en"), clean_profile.get("cons_ar"))
            clean_profile["pros_en"] = p_en
            clean_profile["pros_ar"] = p_ar
            clean_profile["cons_en"] = c_en
            clean_profile["cons_ar"] = c_ar

            canonical_ids = list(item.get("matched_canonical_ids") or [])
            for fallback_id in (item.get("primary_canonical_id"), item.get("canonical_id")):
                if fallback_id and fallback_id not in canonical_ids:
                    canonical_ids.append(fallback_id)

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
        return to_review_input(laptop)

    @staticmethod
    def _to_review_target(target: ResolvedReviewTarget) -> LaptopReviewTarget:
        return to_review_target(target)


__all__ = ["ReviewIngestionResult", "ReviewIntelligenceService"]
