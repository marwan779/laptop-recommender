"""Application pipeline orchestrating S3 raw reviews -> enrichment -> Chroma -> S3.

Coordinates external boundaries via Dependency Inversion (storage, enrichment,
optional deduplication hook, vector store, and live recommendation reloader).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Any, Dict, Optional, Protocol

from app.common.logger import get_logger
from app.common.storage.base import IObjectStorageService
from app.common.storage.factory import get_storage_service
from app.domain.enrichment.chunking import detect_reviews_format
from app.infrastructure.chroma_repository import CHROMA_DEFAULT_DIR, ChromaReviewsRepository
from app.infrastructure.jina_embedder import MODEL_NAME
from app.infrastructure.protocols import IReviewsVectorStore
from app.schemas.events import ReviewsEnrichedPayload
from app.services.recommendation_service import RecommendationService, get_recommendation_service
from app.services.reviews_enrichment_service import ReviewsEnrichmentService

logger = get_logger("ai_recommender.services.reviews_pipeline")


class IReviewsDeduplicator(Protocol):
    """Pluggable contract for Stage 2 review deduplication/audit preprocessing."""

    def deduplicate(
        self,
        payload: Dict[str, Any],
        catalog_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return deduplicated Format B2 payload or pass through unchanged."""
        ...


class OptionalAuditDeduplicator:
    """Adapter for `audit_and_deduplicate_reviews` when available; skips safely otherwise."""

    def deduplicate(
        self,
        payload: Dict[str, Any],
        catalog_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        fmt = detect_reviews_format(payload)
        if fmt == "format_b2_deduplicated":
            return payload

        if importlib.util.find_spec("audit_and_deduplicate_reviews") is None:
            logger.info(
                "Optional module 'audit_and_deduplicate_reviews' is not present; "
                "proceeding directly with enriched Format B1 payload."
            )
            return payload

        from audit_and_deduplicate_reviews import run_audit_and_dedup

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            b1_path = tmp / "enriched_b1.json"
            b2_path = tmp / "deduplicated_b2.json"
            tasks_md = tmp / "gap_tasks.md"
            b1_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            run_audit_and_dedup(
                reviews_in=str(b1_path),
                catalog_in=catalog_path or "unified_catalog_topsis_ready_v6.json",
                dedup_out=str(b2_path),
                tasks_md_out=str(tasks_md),
            )
            if not b2_path.exists():
                return payload
            return json.loads(b2_path.read_text(encoding="utf-8"))


class ReviewsPipelineService:
    """Use-case service running the end-to-end review enrichment & Chroma indexing job."""

    def __init__(
        self,
        storage_service: Optional[IObjectStorageService] = None,
        enrichment_service: Optional[ReviewsEnrichmentService] = None,
        vector_store: Optional[IReviewsVectorStore] = None,
        deduplicator: Optional[IReviewsDeduplicator] = None,
        recommendation_service: Optional[RecommendationService] = None,
        chroma_dir: str = CHROMA_DEFAULT_DIR,
        model_name: str = MODEL_NAME,
        enricher_mode: str = "primary_with_fallback",
        catalog_path: str = "unified_catalog_topsis_ready_v6.json",
    ) -> None:
        self._storage_service = storage_service
        self._enrichment_service = enrichment_service
        self._vector_store = vector_store
        self._deduplicator = deduplicator or OptionalAuditDeduplicator()
        self._recommendation_service = recommendation_service
        self.chroma_dir = chroma_dir
        self.model_name = model_name
        self.enricher_mode = enricher_mode
        self.catalog_path = catalog_path

    def _resolve_storage_service(self) -> IObjectStorageService:
        if self._storage_service is None:
            self._storage_service = get_storage_service()
        return self._storage_service

    def _resolve_enrichment_service(self) -> ReviewsEnrichmentService:
        if self._enrichment_service is None:
            self._enrichment_service = ReviewsEnrichmentService()
        return self._enrichment_service

    def _resolve_vector_store(self) -> IReviewsVectorStore:
        if self._vector_store is None:
            self._vector_store = ChromaReviewsRepository()
        return self._vector_store

    def _resolve_recommendation_service(self) -> RecommendationService:
        if self._recommendation_service is None:
            self._recommendation_service = get_recommendation_service()
        return self._recommendation_service

    def _enrich_and_index_sync(
        self,
        raw_payload: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Run CPU/LLM enrichment, optional deduplication, and incremental Chroma upsert."""
        fmt = detect_reviews_format(raw_payload)
        if fmt == "format_a_raw":
            enriched_payload, _ = self._resolve_enrichment_service().enrich_reviews_dataset(
                payload_or_path=raw_payload,
                catalog_path=self.catalog_path,
                mode=self.enricher_mode,
                output_path=None,
            )
        else:
            enriched_payload = raw_payload

        processed_payload = self._deduplicator.deduplicate(
            enriched_payload,
            catalog_path=self.catalog_path,
        )
        index_summary = self._resolve_vector_store().upsert_reviews(
            processed_payload,
            chroma_dir=self.chroma_dir,
            model_name=self.model_name,
        )
        return processed_payload, index_summary

    @staticmethod
    def _count_chassis_and_laptops(
        payload: Dict[str, Any],
        index_summary: Dict[str, Any],
    ) -> tuple[int, int]:
        """Count unique chassis processed and matched catalog laptop canonical IDs."""
        items = payload.get("chassis_reviews")
        if not isinstance(items, list):
            items = payload.get("laptops") if isinstance(payload.get("laptops"), list) else []

        total_chassis = len(items)
        unique_cids: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            for cid in item.get("matched_canonical_ids") or []:
                if cid:
                    unique_cids.add(str(cid))
            for fallback_key in ("primary_canonical_id", "canonical_id"):
                cid = item.get(fallback_key)
                if cid:
                    unique_cids.add(str(cid))

        summary_count = int(index_summary.get("updated_laptops_count") or 0)
        return total_chassis, max(len(unique_cids), summary_count)

    async def process_reviews_ready(
        self,
        *,
        job_id: str,
        s3_key: str,
    ) -> ReviewsEnrichedPayload:
        """Download raw S3 reviews, enrich + upsert ChromaDB, upload artifact, and refresh live state."""
        storage = self._resolve_storage_service()
        raw_payload = await asyncio.to_thread(storage.read_json, s3_key)
        if not isinstance(raw_payload, dict):
            raise ValueError(f"Expected JSON object in '{s3_key}', got {type(raw_payload).__name__}.")

        processed_payload, index_summary = await asyncio.to_thread(
            self._enrich_and_index_sync,
            raw_payload,
        )

        enriched_s3_key = f"reviews/enriched/{job_id}.json"
        await asyncio.to_thread(
            storage.upload_json,
            processed_payload,
            enriched_s3_key,
            {"job_id": job_id, "source_s3_key": s3_key},
        )

        await asyncio.to_thread(
            self._resolve_recommendation_service().refresh_reviews_state,
            self.chroma_dir,
            processed_payload,
        )

        total_chassis, total_laptops = self._count_chassis_and_laptops(
            processed_payload,
            index_summary,
        )
        logger.info(
            "Processed reviews batch [job_id=%s, source=%s -> enriched=%s, chassis=%d, laptops=%d]",
            job_id,
            s3_key,
            enriched_s3_key,
            total_chassis,
            total_laptops,
        )
        return ReviewsEnrichedPayload(
            job_id=job_id,
            s3_key=enriched_s3_key,
            s3_bucket=storage.bucket_name,
            total_chassis=total_chassis,
            total_laptops=total_laptops,
        )


__all__ = [
    "IReviewsDeduplicator",
    "OptionalAuditDeduplicator",
    "ReviewsPipelineService",
]
