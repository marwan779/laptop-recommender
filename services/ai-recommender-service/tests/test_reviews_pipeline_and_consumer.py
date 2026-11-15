"""Unit & integration tests for the Stage 2 AI reviews pipeline & consumer."""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.common.cache.memory import InMemoryCacheProvider
from app.infrastructure.chroma_repository import ChromaReviewsRepository
from app.schemas.events import (
    EventType,
    ReviewsEnrichFailedEvent,
    ReviewsEnrichedEvent,
    ReviewsEnrichedPayload,
    ReviewsReadyEvent,
)
from app.services.messaging_consumer import AIRecommenderMessageConsumer
from app.services.reviews_pipeline_service import (
    DomainReviewsDeduplicator,
    ReviewsPipelineService,
)


def _sample_format_a_payload(
    *,
    chassis_key: str = "lenovo|legion_5",
    primary_cid: str = "cid-1",
    matched_cids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    cids = matched_cids if matched_cids is not None else [primary_cid]
    return {
        "batch_metadata": {"job_id": "job-test", "total_chassis": 1},
        "laptops": [
            {
                "chassis_key": chassis_key,
                "primary_canonical_id": primary_cid,
                "matched_canonical_ids": cids,
                "identity": {"brand": "Lenovo", "laptop_model": "Legion 5"},
                "specs": {"cpu": {"model": "i7-13650HX"}},
                "youtube": [],
                "communities": [],
            }
        ],
    }


def _sample_format_b1_item(
    *,
    canonical_id: str,
    chassis_key: str = "lenovo|legion_5",
    brand: str = "Lenovo",
    model_name: str = "Legion 5",
    pro_text: str = "Strong sustained cooling under load.",
) -> Dict[str, Any]:
    return {
        "chassis_key": chassis_key,
        "canonical_id": canonical_id,
        "primary_canonical_id": canonical_id,
        "matched_canonical_ids": [canonical_id],
        "identity": {"brand": brand, "laptop_model": model_name},
        "nlp_review_profile": {
            "community_nlp_score": 82.0,
            "aspect_scores": {
                "gaming": 9.0,
                "thermals": 8.5,
                "display": 8.0,
                "battery": 6.5,
            },
            "pros_en": [pro_text],
            "cons_en": ["Heavy 2.4kg chassis."],
            "pros_ar": ["تبريد ممتاز تحت الضغط."],
            "cons_ar": ["الوزن ثقيل نسبياً."],
        },
    }


def test_event_schemas_roundtrip_and_defaults() -> None:
    ready_raw = {
        "event_id": "evt-1",
        "correlation_id": "corr-123",
        "payload": {
            "job_id": "job-42",
            "total_laptops": 5,
            "total_chassis": 2,
            "total_snippets": 18,
            "s3_key": "reviews/raw/job-42.json",
            "results": [],
        },
    }
    ready = ReviewsReadyEvent.model_validate(ready_raw)
    assert ready.event_type == EventType.REVIEWS_READY_EVENT
    assert ready.payload.job_id == "job-42"
    assert ready.payload.s3_key == "reviews/raw/job-42.json"

    enriched = ReviewsEnrichedEvent(
        correlation_id=ready.correlation_id,
        payload=ReviewsEnrichedPayload(
            job_id="job-42",
            s3_key="reviews/enriched/job-42.json",
            s3_bucket="laptop-data",
            total_chassis=2,
            total_laptops=5,
        ),
    )
    assert enriched.event_type == EventType.REVIEWS_ENRICHED_EVENT
    dumped = enriched.model_dump(mode="json")
    assert dumped["payload"]["s3_key"] == "reviews/enriched/job-42.json"

    failed = ReviewsEnrichFailedEvent(
        correlation_id=ready.correlation_id,
        payload={
            "job_id": "job-42",
            "error_message": "boom",
            "s3_key": "reviews/raw/job-42.json",
            "details": {"exception_type": "RuntimeError"},
        },
    )
    assert failed.event_type == EventType.REVIEWS_ENRICH_FAILED_EVENT
    assert failed.payload.error_message == "boom"


def test_chroma_repository_upsert_reviews_is_incremental(monkeypatch: pytest.MonkeyPatch) -> None:
    collections: Dict[str, Any] = {}
    deleted_collections: List[str] = []

    class FakeCollection:
        def __init__(self, name: str) -> None:
            self.name = name
            self.records: Dict[str, Dict[str, Any]] = {}

        def get(self, include: Any = None) -> Dict[str, Any]:
            return {"ids": list(self.records.keys())}

        def upsert(
            self,
            *,
            ids: List[str],
            documents: List[str],
            metadatas: List[Dict[str, Any]],
        ) -> None:
            for doc_id, doc_text, meta in zip(ids, documents, metadatas):
                self.records[doc_id] = {"document": doc_text, "metadata": meta}

    class FakePersistentClient:
        def __init__(self, path: str) -> None:
            self.path = path

        def delete_collection(self, name: str) -> None:
            deleted_collections.append(name)
            collections.pop(name, None)

        def create_collection(
            self,
            name: str,
            embedding_function: Any = None,
            metadata: Any = None,
        ) -> FakeCollection:
            collections[name] = FakeCollection(name)
            return collections[name]

        def get_or_create_collection(
            self,
            name: str,
            embedding_function: Any = None,
            metadata: Any = None,
        ) -> FakeCollection:
            if name not in collections:
                collections[name] = FakeCollection(name)
            return collections[name]

    fake_chromadb = types.ModuleType("chromadb")
    fake_chromadb.PersistentClient = FakePersistentClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)
    monkeypatch.setattr(
        "app.infrastructure.chroma_repository.JinaV3EmbeddingFunction",
        lambda *args, **kwargs: object(),
    )

    repo = ChromaReviewsRepository()

    batch_1 = {
        "laptops": [
            _sample_format_b1_item(
                canonical_id="cid-1",
                chassis_key="lenovo|legion_5",
                model_name="Legion 5",
            )
        ]
    }
    summary_1 = repo.upsert_reviews(batch_1, chroma_dir="./tmp_chroma", model_name="fake-jina")
    assert summary_1["updated_laptops_count"] == 1
    assert deleted_collections == []
    col = next(iter(collections.values()))
    batch_1_doc_ids = set(col.records.keys())
    assert "lenovo|legion_5__pro" in batch_1_doc_ids
    assert "lenovo|legion_5__con" in batch_1_doc_ids

    batch_2 = {
        "laptops": [
            _sample_format_b1_item(
                canonical_id="cid-2",
                chassis_key="lenovo|loq_15",
                model_name="LOQ 15",
            )
        ]
    }
    summary_2 = repo.upsert_reviews(batch_2, chroma_dir="./tmp_chroma", model_name="fake-jina")
    assert summary_2["updated_laptops_count"] == 1
    assert deleted_collections == []

    all_doc_ids = set(col.records.keys())
    assert batch_1_doc_ids.issubset(all_doc_ids)
    assert "lenovo|loq_15__pro" in all_doc_ids
    assert "lenovo|loq_15__con" in all_doc_ids

    # Full rebuild still recreates cleanly.
    repo.build(batch_2, chroma_dir="./tmp_chroma", model_name="fake-jina")
    assert len(deleted_collections) == 1
    rebuilt_col = next(iter(collections.values()))
    assert "lenovo|legion_5__pro" not in rebuilt_col.records
    assert "lenovo|loq_15__pro" in rebuilt_col.records


def test_domain_reviews_deduplicator_dedupes_b1_to_b2_and_passes_b2() -> None:
    dedup = DomainReviewsDeduplicator()

    b1_payload = {
        "laptops": [_sample_format_b1_item(canonical_id="cid-1")],
    }
    b2_out = dedup.deduplicate(b1_payload)
    assert isinstance(b2_out.get("chassis_reviews"), list)
    assert len(b2_out["chassis_reviews"]) == 1
    entry = b2_out["chassis_reviews"][0]
    assert entry["chassis_key"] == "lenovo|legion_5"
    assert entry["community_nlp_score"] == 82.0
    assert entry["aspect_scores"]["thermals"] == 8.5

    b2_payload = {
        "chassis_reviews": [{"chassis_key": "lenovo|legion_5", "matched_canonical_ids": ["cid-1"]}],
    }
    assert dedup.deduplicate(b2_payload) is b2_payload


def test_pipeline_process_reviews_ready_end_to_end() -> None:
    raw_payload = _sample_format_a_payload(
        primary_cid="cid-1",
        matched_cids=["cid-1", "cid-2"],
    )
    enriched_payload = {
        "batch_metadata": {"job_id": "job-99"},
        "laptops": [
            {
                **_sample_format_b1_item(canonical_id="cid-1"),
                "matched_canonical_ids": ["cid-1", "cid-2"],
            }
        ],
    }

    uploaded: Dict[str, Any] = {}

    class FakeStorage:
        bucket_name = "laptop-recommender-bucket"

        def read_json(self, s3_key: str) -> Dict[str, Any]:
            assert s3_key == "reviews/raw/job-99.json"
            return raw_payload

        def upload_json(
            self,
            payload: Dict[str, Any],
            s3_key: str,
            metadata: Optional[Dict[str, str]] = None,
        ) -> str:
            uploaded["payload"] = payload
            uploaded["s3_key"] = s3_key
            uploaded["metadata"] = metadata
            return s3_key

    enrichment_calls: List[Dict[str, Any]] = []

    class FakeEnrichmentService:
        def enrich_reviews_dataset(
            self,
            *,
            payload_or_path: Any,
            catalog_path: str,
            mode: str,
            output_path: Optional[str],
        ) -> tuple[Dict[str, Any], Dict[str, Any]]:
            enrichment_calls.append(
                {
                    "payload_or_path": payload_or_path,
                    "catalog_path": catalog_path,
                    "mode": mode,
                    "output_path": output_path,
                }
            )
            return enriched_payload, {"enriched": 1}

    vector_calls: List[Dict[str, Any]] = []

    class FakeVectorStore:
        def build(self, data: Dict[str, Any], chroma_dir: str, model_name: str) -> Dict[str, Any]:
            raise AssertionError("Pipeline must use incremental upsert_reviews, not build.")

        def upsert_reviews(
            self,
            data: Dict[str, Any],
            chroma_dir: str,
            model_name: str,
        ) -> Dict[str, Any]:
            vector_calls.append({"data": data, "chroma_dir": chroma_dir, "model_name": model_name})
            return {
                "indexed_documents_count": 3,
                "updated_laptops_count": 2,
                "profiles_by_canonical_id": {"cid-1": {}, "cid-2": {}},
            }

    refresh_calls: List[tuple[str, Optional[Dict[str, Any]]]] = []

    class FakeRecommendationService:
        def refresh_reviews_state(
            self,
            chroma_dir: str,
            enriched_payload: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            refresh_calls.append((chroma_dir, enriched_payload))
            return {"loaded_profiles": 2}

    pipeline = ReviewsPipelineService(
        storage_service=FakeStorage(),  # type: ignore[arg-type]
        enrichment_service=FakeEnrichmentService(),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        recommendation_service=FakeRecommendationService(),  # type: ignore[arg-type]
        chroma_dir="./test_chroma",
        model_name="fake-jina-v3",
    )

    result = asyncio.run(
        pipeline.process_reviews_ready(
            job_id="job-99",
            s3_key="reviews/raw/job-99.json",
        )
    )

    assert len(enrichment_calls) == 1
    assert enrichment_calls[0]["mode"] == "primary_with_fallback"
    assert enrichment_calls[0]["output_path"] is None

    assert len(vector_calls) == 1
    assert vector_calls[0]["chroma_dir"] == "./test_chroma"
    assert uploaded["s3_key"] == "reviews/enriched/job-99.json"
    processed = uploaded["payload"]
    assert isinstance(processed.get("chassis_reviews"), list)
    assert len(processed["chassis_reviews"]) == 1
    assert processed["chassis_reviews"][0]["matched_canonical_ids"] == ["cid-1", "cid-2"]
    assert processed["chassis_reviews"][0]["community_nlp_score"] == 82.0
    assert refresh_calls == [("./test_chroma", processed)]

    assert result.job_id == "job-99"
    assert result.s3_key == "reviews/enriched/job-99.json"
    assert result.s3_bucket == "laptop-recommender-bucket"
    assert result.total_chassis == 1
    assert result.total_laptops == 2


def test_consumer_start_listening_subscribes_with_prefetch_one() -> None:
    async def _run() -> None:
        broker = MagicMock()
        broker.subscribe = AsyncMock()
        consumer = AIRecommenderMessageConsumer(broker=broker)

        await consumer.start_listening()
        await consumer.start_listening()  # idempotent second call

        broker.subscribe.assert_awaited_once_with(
            queue_name="ai.reviews.ready.jobs",
            routing_key=EventType.REVIEWS_READY_EVENT,
            handler=consumer.handle_reviews_ready_event,
            prefetch_count=1,
        )

    asyncio.run(_run())


def test_consumer_skips_empty_s3_key_and_duplicate_inbox() -> None:
    async def _run() -> None:
        broker = MagicMock()
        broker.publish = AsyncMock()
        inbox = MagicMock()
        inbox.claim_message = AsyncMock(return_value=False)
        pipeline = MagicMock()
        pipeline.process_reviews_ready = AsyncMock()

        consumer = AIRecommenderMessageConsumer(
            broker=broker,
            inbox=inbox,
            pipeline_service=pipeline,
        )

        # 1. Empty s3_key -> skip completely before inbox claim
        await consumer.handle_reviews_ready_event(
            {
                "event_id": "evt-empty",
                "correlation_id": "corr-empty",
                "payload": {"job_id": "job-empty", "s3_key": None},
            }
        )
        inbox.claim_message.assert_not_awaited()
        pipeline.process_reviews_ready.assert_not_awaited()

        # 2. Duplicate inbox -> claim returns False, skip processing
        await consumer.handle_reviews_ready_event(
            {
                "event_id": "evt-dup",
                "correlation_id": "corr-dup",
                "payload": {"job_id": "job-dup", "s3_key": "reviews/raw/job-dup.json"},
            }
        )
        inbox.claim_message.assert_awaited_once_with("evt-dup", EventType.REVIEWS_READY_EVENT)
        pipeline.process_reviews_ready.assert_not_awaited()
        broker.publish.assert_not_awaited()

    asyncio.run(_run())


def test_consumer_happy_path_publishes_enriched_and_marks_completed() -> None:
    async def _run() -> None:
        broker = MagicMock()
        broker.publish = AsyncMock()
        inbox = MagicMock()
        inbox.claim_message = AsyncMock(return_value=True)
        inbox.mark_completed = AsyncMock()
        inbox.release_claim = AsyncMock()

        enriched_payload = ReviewsEnrichedPayload(
            job_id="job-ok",
            s3_key="reviews/enriched/job-ok.json",
            s3_bucket="laptop-data",
            total_chassis=1,
            total_laptops=2,
        )
        pipeline = MagicMock()
        pipeline.process_reviews_ready = AsyncMock(return_value=enriched_payload)

        consumer = AIRecommenderMessageConsumer(
            broker=broker,
            inbox=inbox,
            pipeline_service=pipeline,
        )

        await consumer.handle_reviews_ready_event(
            {
                "event_id": "evt-ok",
                "correlation_id": "corr-ok",
                "payload": {
                    "job_id": "job-ok",
                    "total_laptops": 2,
                    "total_chassis": 1,
                    "s3_key": "reviews/raw/job-ok.json",
                },
            }
        )

        pipeline.process_reviews_ready.assert_awaited_once_with(
            job_id="job-ok",
            s3_key="reviews/raw/job-ok.json",
        )
        broker.publish.assert_awaited_once()
        pub_kwargs = broker.publish.call_args.kwargs
        assert pub_kwargs["routing_key"] == EventType.REVIEWS_ENRICHED_EVENT
        published_event = pub_kwargs["message"]
        assert isinstance(published_event, ReviewsEnrichedEvent)
        assert published_event.correlation_id == "corr-ok"
        assert published_event.payload.s3_key == "reviews/enriched/job-ok.json"

        inbox.mark_completed.assert_awaited_once_with("evt-ok")
        inbox.release_claim.assert_not_awaited()

    asyncio.run(_run())


def test_consumer_failure_path_publishes_failed_event_releases_claim_and_reraises() -> None:
    async def _run() -> None:
        broker = MagicMock()
        broker.publish = AsyncMock()
        inbox = MagicMock()
        inbox.claim_message = AsyncMock(return_value=True)
        inbox.mark_completed = AsyncMock()
        inbox.release_claim = AsyncMock()

        pipeline = MagicMock()
        pipeline.process_reviews_ready = AsyncMock(side_effect=RuntimeError("S3 timeout"))

        consumer = AIRecommenderMessageConsumer(
            broker=broker,
            inbox=inbox,
            pipeline_service=pipeline,
        )

        with pytest.raises(RuntimeError, match="S3 timeout"):
            await consumer.handle_reviews_ready_event(
                {
                    "event_id": "evt-fail",
                    "correlation_id": "corr-fail",
                    "payload": {
                        "job_id": "job-fail",
                        "total_laptops": 3,
                        "total_chassis": 1,
                        "s3_key": "reviews/raw/job-fail.json",
                    },
                }
            )

        broker.publish.assert_awaited_once()
        pub_kwargs = broker.publish.call_args.kwargs
        assert pub_kwargs["routing_key"] == EventType.REVIEWS_ENRICH_FAILED_EVENT
        failed_event = pub_kwargs["message"]
        assert isinstance(failed_event, ReviewsEnrichFailedEvent)
        assert failed_event.correlation_id == "corr-fail"
        assert failed_event.payload.job_id == "job-fail"
        assert failed_event.payload.s3_key == "reviews/raw/job-fail.json"
        assert failed_event.payload.error_message == "S3 timeout"

        inbox.release_claim.assert_awaited_once_with("evt-fail")
        inbox.mark_completed.assert_not_awaited()

    asyncio.run(_run())


def test_fastapi_lifespan_falls_back_gracefully_without_redis_or_rabbitmq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.app as api_app

    class OfflineRedisCache:
        async def connect(self) -> None:
            return None

        async def health_check(self) -> bool:
            return False

        async def close(self) -> None:
            return None

    class OfflineBroker:
        is_connected = False

        async def connect(self) -> None:
            raise ConnectionError("RabbitMQ offline")

        async def close(self) -> None:
            return None

    monkeypatch.setattr(api_app, "_get_service", lambda: object())
    monkeypatch.setattr(api_app, "RedisCacheProvider", OfflineRedisCache)
    monkeypatch.setattr(api_app, "RabbitMQBroker", OfflineBroker)

    async def _run() -> None:
        async with api_app.lifespan(api_app.app):
            assert isinstance(api_app.app.state.cache, InMemoryCacheProvider)
            assert isinstance(api_app.app.state.consumer, AIRecommenderMessageConsumer)

    asyncio.run(_run())
