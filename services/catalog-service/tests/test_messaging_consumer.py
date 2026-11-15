"""Unit tests for CatalogMessageConsumer."""

from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest

from app.models.scraping import ScrapingBatchLog
from app.schemas.events import (
    CatalogReadyEvent,
    CatalogReadyPayload,
    CatalogScrapeFailedEvent,
    CatalogScrapeFailedPayload,
    EventType,
    PricesCheckedEvent,
    PricesCheckedPayload,
    ReviewsEnrichedEvent,
    ReviewsEnrichedPayload,
    ReviewsEnrichFailedEvent,
    ReviewsEnrichFailedPayload,
)
from app.schemas.price_sync import PriceChangeType, PriceCheckItemResult, PriceSyncSummary
from app.services.catalog_ingestion_service import IngestionResult
from app.services.messaging_consumer import CatalogMessageConsumer
from app.services.review_intelligence_service import ReviewIngestionResult


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.begin = MagicMock()

    # Default inbox claim result: the message is new and can be processed.
    claim_result = MagicMock()
    claim_result.scalar_one_or_none.return_value = "claimed-event-id"
    session.execute.return_value = claim_result

    class FakeBeginCM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    session.begin.return_value = FakeBeginCM()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    class FakeSessionCM:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    return lambda: FakeSessionCM()


@pytest.mark.asyncio
async def test_consumer_start_listening():
    mock_broker = AsyncMock()
    consumer = CatalogMessageConsumer(broker=mock_broker)

    await consumer.start_listening()

    assert mock_broker.subscribe.call_count == 5
    subscriptions = {
        call.kwargs["queue_name"]: call.kwargs["routing_key"] for call in mock_broker.subscribe.call_args_list
    }

    assert subscriptions["catalog.ready.jobs"] == EventType.CATALOG_READY_EVENT
    assert subscriptions["catalog.scrape.failed.jobs"] == EventType.CATALOG_SCRAPE_FAILED_EVENT
    assert subscriptions["catalog.prices.checked.jobs"] == EventType.PRICES_CHECKED_EVENT
    assert subscriptions["catalog.reviews.enriched.jobs"] == EventType.REVIEWS_ENRICHED_EVENT
    assert subscriptions["catalog.reviews.enrich.failed.jobs"] == EventType.REVIEWS_ENRICH_FAILED_EVENT


@pytest.mark.asyncio
async def test_handle_catalog_ready_event_success(mock_session_factory):
    mock_broker = AsyncMock()
    mock_ingestion = AsyncMock()

    batch_id = uuid.uuid4()
    mock_ingestion.ingest_from_s3.return_value = IngestionResult(
        batch_id=batch_id,
        status="SUCCESS",
        source="s3://test-bucket/catalogs/catalog_1.json",
        duration_seconds=12.5,
        total_laptops=100,
        new_laptops=10,
        updated_laptops=90,
        offers_created=10,
        offers_updated=90,
        metrics_created=10,
        metrics_updated=90,
        metrics_summary={},
    )

    consumer = CatalogMessageConsumer(
        broker=mock_broker,
        session_factory=mock_session_factory,
        ingestion_service=mock_ingestion,
    )

    event = CatalogReadyEvent(
        payload=CatalogReadyPayload(
            batch_id=str(batch_id),
            s3_bucket="test-bucket",
            s3_key="catalogs/catalog_1.json",
            total_laptops=100,
        )
    )

    await consumer.handle_catalog_ready_event(event.model_dump())

    mock_ingestion.ingest_from_s3.assert_called_once()
    call_kwargs = mock_ingestion.ingest_from_s3.call_args.kwargs
    assert call_kwargs["s3_key"] == "catalogs/catalog_1.json"
    assert call_kwargs["batch_id"] == batch_id


@pytest.mark.asyncio
async def test_handle_catalog_ready_event_failure_raises(mock_session_factory):
    mock_broker = AsyncMock()
    mock_ingestion = AsyncMock()

    batch_id = uuid.uuid4()
    mock_ingestion.ingest_from_s3.return_value = IngestionResult(
        batch_id=batch_id,
        status="FAILED",
        source="s3://test-bucket/catalogs/catalog_1.json",
        duration_seconds=1.2,
        total_laptops=0,
        new_laptops=0,
        updated_laptops=0,
        offers_created=0,
        offers_updated=0,
        metrics_created=0,
        metrics_updated=0,
        metrics_summary={},
        error_message="Corrupted JSON in S3",
    )

    consumer = CatalogMessageConsumer(
        broker=mock_broker,
        session_factory=mock_session_factory,
        ingestion_service=mock_ingestion,
    )

    event = CatalogReadyEvent(
        payload=CatalogReadyPayload(
            batch_id=str(batch_id),
            s3_bucket="test-bucket",
            s3_key="catalogs/catalog_1.json",
            total_laptops=100,
        )
    )

    with pytest.raises(RuntimeError, match="Corrupted JSON in S3"):
        await consumer.handle_catalog_ready_event(event.model_dump())


@pytest.mark.asyncio
async def test_handle_catalog_scrape_failed(mock_session, mock_session_factory):
    mock_broker = AsyncMock()
    batch_id = uuid.uuid4()

    existing_log = ScrapingBatchLog(
        id=batch_id,
        store_key="compumarts",
        trigger_type="CRON",
        status="QUEUED",
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_log
    mock_session.execute.return_value = mock_result

    consumer = CatalogMessageConsumer(
        broker=mock_broker,
        session_factory=mock_session_factory,
    )

    event = CatalogScrapeFailedEvent(
        payload=CatalogScrapeFailedPayload(
            batch_id=str(batch_id),
            error_message="Failed to connect to compumarts.com after 3 retries",
        )
    )

    await consumer.handle_catalog_scrape_failed(event.model_dump())

    assert existing_log.status == "FAILED"
    assert "Failed to connect" in existing_log.error_message


@pytest.mark.asyncio
async def test_handle_prices_checked_event(mock_session_factory):
    mock_broker = AsyncMock()
    mock_price_sync = AsyncMock()
    mock_price_sync.apply_batch_results.return_value = PriceSyncSummary(
        batch_id="batch-p1",
        store_key="compumarts",
        total_processed=1,
        offers_updated=1,
        price_drops_detected=1,
    )

    consumer = CatalogMessageConsumer(
        broker=mock_broker,
        session_factory=mock_session_factory,
        price_sync_service=mock_price_sync,
    )

    event = PricesCheckedEvent(
        payload=PricesCheckedPayload(
            batch_id="batch-p1",
            store_key="compumarts",
            total_items=1,
            changed_items_count=1,
            price_drops_count=1,
            results=[
                PriceCheckItemResult(
                    offer_id=str(uuid.uuid4()),
                    laptop_id=str(uuid.uuid4()),
                    product_url="https://compumarts.com/p",
                    old_price_egp=50000.0,
                    new_price_egp=48000.0,
                    old_in_stock=True,
                    new_in_stock=True,
                    has_changed=True,
                    change_type=PriceChangeType.PRICE_DROP,
                    price_delta_egp=-2000.0,
                )
            ],
        )
    )

    await consumer.handle_prices_checked_event(event.model_dump())

    mock_price_sync.apply_batch_results.assert_called_once()
    assert mock_price_sync.apply_batch_results.call_args.kwargs["commit"] is False
    mock_price_sync.invalidate_caches.assert_not_called()


@pytest.mark.asyncio
async def test_handle_prices_checked_event_invalidates_cache_after_commit(
    mock_session, mock_session_factory
):
    execution_order: list[str] = []
    affected_id = uuid.uuid4()

    class TrackingBeginCM:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            execution_order.append("tx_exit")
            return None

    mock_session.begin.return_value = TrackingBeginCM()

    mock_broker = AsyncMock()
    mock_price_sync = AsyncMock()
    mock_price_sync.apply_batch_results.return_value = PriceSyncSummary(
        batch_id="batch-p2",
        store_key="compumarts",
        total_processed=1,
        offers_updated=1,
        price_drops_detected=1,
        affected_laptop_ids=[affected_id],
    )

    async def record_invalidate(session, laptop_ids):
        execution_order.append("cache_invalidate")

    mock_price_sync.invalidate_caches.side_effect = record_invalidate

    consumer = CatalogMessageConsumer(
        broker=mock_broker,
        session_factory=mock_session_factory,
        price_sync_service=mock_price_sync,
    )

    event = PricesCheckedEvent(
        payload=PricesCheckedPayload(
            batch_id="batch-p2",
            store_key="compumarts",
            total_items=1,
            changed_items_count=1,
            price_drops_count=1,
            results=[
                PriceCheckItemResult(
                    offer_id=str(uuid.uuid4()),
                    laptop_id=str(affected_id),
                    product_url="https://compumarts.com/p",
                    old_price_egp=50000.0,
                    new_price_egp=48000.0,
                    old_in_stock=True,
                    new_in_stock=True,
                    has_changed=True,
                    change_type=PriceChangeType.PRICE_DROP,
                    price_delta_egp=-2000.0,
                )
            ],
        )
    )

    await consumer.handle_prices_checked_event(event.model_dump())

    mock_price_sync.apply_batch_results.assert_called_once()
    assert mock_price_sync.apply_batch_results.call_args.kwargs["commit"] is False
    mock_price_sync.invalidate_caches.assert_awaited_once_with(mock_session, [affected_id])
    assert execution_order == ["tx_exit", "cache_invalidate"]


@pytest.mark.asyncio
async def test_handle_reviews_enriched_event():
    mock_broker = AsyncMock()
    consumer = CatalogMessageConsumer(broker=mock_broker)

    event = ReviewsEnrichedEvent(
        payload=ReviewsEnrichedPayload(
            job_id="job-rec-1",
            total_chassis=1,
            total_laptops=1,
            s3_key="",
        )
    )

    # Should not raise when s3_key is empty
    await consumer.handle_reviews_enriched_event(event.model_dump())


@pytest.mark.asyncio
async def test_handle_reviews_enriched_event_defers_commit_to_outer_transaction(
    mock_session,
    mock_session_factory,
):
    mock_broker = AsyncMock()
    mock_review_service = AsyncMock()

    consumer = CatalogMessageConsumer(
        broker=mock_broker,
        session_factory=mock_session_factory,
        review_intelligence_service=mock_review_service,
    )

    event = ReviewsEnrichedEvent(
        payload=ReviewsEnrichedPayload(
            job_id="job-rec-2",
            total_chassis=1,
            total_laptops=1,
            s3_key="reviews/batch_1.json",
        )
    )

    await consumer.handle_reviews_enriched_event(event.model_dump())

    mock_review_service.ingest_from_s3.assert_awaited_once_with(
        session=mock_session,
        s3_key="reviews/batch_1.json",
        commit=False,
    )


@pytest.mark.asyncio
async def test_handle_catalog_ready_event_invalidates_caches_after_commit(
    mock_session,
    mock_session_factory,
):
    execution_order: list[str] = []

    class TrackingBeginCM:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            execution_order.append("tx_exit")
            return None

    mock_session.begin.return_value = TrackingBeginCM()

    cleared_prefixes: list[str] = []
    mock_cache = AsyncMock()

    async def track_clear(prefix: str) -> int:
        execution_order.append("cache_invalidate")
        cleared_prefixes.append(prefix)
        return 1

    mock_cache.clear_prefix.side_effect = track_clear

    batch_id = uuid.uuid4()
    mock_ingestion = AsyncMock()
    mock_ingestion.ingest_from_s3.return_value = IngestionResult(
        batch_id=batch_id,
        status="SUCCESS",
        source="s3://test-bucket/catalogs/catalog_1.json",
        duration_seconds=5.0,
        total_laptops=10,
        new_laptops=5,
        updated_laptops=5,
        offers_created=5,
        offers_updated=5,
        metrics_created=5,
        metrics_updated=5,
        metrics_summary={},
    )

    consumer = CatalogMessageConsumer(
        broker=AsyncMock(),
        session_factory=mock_session_factory,
        ingestion_service=mock_ingestion,
        cache=mock_cache,
    )

    event = CatalogReadyEvent(
        payload=CatalogReadyPayload(
            batch_id=str(batch_id),
            s3_bucket="test-bucket",
            s3_key="catalogs/catalog_1.json",
            total_laptops=10,
        )
    )

    await consumer.handle_catalog_ready_event(event.model_dump())

    assert execution_order[0] == "tx_exit"
    assert set(cleared_prefixes) == {
        "catalog:browse",
        "catalog:laptop",
        "catalog:recommendation",
        "catalog:price_history",
    }


@pytest.mark.asyncio
async def test_handle_reviews_enriched_event_invalidates_caches_after_commit(
    mock_session,
    mock_session_factory,
):
    execution_order: list[str] = []

    class TrackingBeginCM:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            execution_order.append("tx_exit")
            return None

    mock_session.begin.return_value = TrackingBeginCM()

    cleared_prefixes: list[str] = []
    mock_cache = AsyncMock()

    async def track_clear(prefix: str) -> int:
        execution_order.append("cache_invalidate")
        if prefix == "catalog:browse":
            raise RuntimeError("redis temporarily unreachable")
        cleared_prefixes.append(prefix)
        return 1

    mock_cache.clear_prefix.side_effect = track_clear

    mock_review_service = AsyncMock()
    mock_review_service.ingest_from_s3.return_value = ReviewIngestionResult(
        status="SUCCESS",
        chassis_processed=3,
        chroma_documents_upserted=0,
        sql_laptops_updated=5,
        duration_seconds=0.4,
    )

    consumer = CatalogMessageConsumer(
        broker=AsyncMock(),
        session_factory=mock_session_factory,
        review_intelligence_service=mock_review_service,
        cache=mock_cache,
    )

    event = ReviewsEnrichedEvent(
        payload=ReviewsEnrichedPayload(
            job_id="reviews_batch_cache_1",
            s3_key="reviews/enriched_cache.json",
            total_chassis=3,
            total_laptops=5,
        )
    )

    await consumer.handle_reviews_enriched_event(event.model_dump())

    assert execution_order[0] == "tx_exit"
    # Fail-open: catalog:browse raised, yet the remaining prefixes still cleared.
    assert cleared_prefixes == ["catalog:laptop", "catalog:recommendation"]


@pytest.mark.asyncio
async def test_handle_reviews_enriched_event_skips_cache_invalidation_when_no_rows_updated(
    mock_session,
    mock_session_factory,
):
    mock_cache = AsyncMock()
    mock_review_service = AsyncMock()
    mock_review_service.ingest_from_s3.return_value = ReviewIngestionResult(
        status="SKIPPED",
        chassis_processed=1,
        chroma_documents_upserted=0,
        sql_laptops_updated=0,
        duration_seconds=0.1,
    )

    consumer = CatalogMessageConsumer(
        broker=AsyncMock(),
        session_factory=mock_session_factory,
        review_intelligence_service=mock_review_service,
        cache=mock_cache,
    )

    event = ReviewsEnrichedEvent(
        payload=ReviewsEnrichedPayload(
            job_id="reviews_batch_noop",
            s3_key="reviews/enriched_noop.json",
        )
    )

    await consumer.handle_reviews_enriched_event(event.model_dump())

    mock_cache.clear_prefix.assert_not_called()


@pytest.mark.asyncio
async def test_handle_reviews_enrich_failed_records_audit_log(
    mock_session,
    mock_session_factory,
):
    from unittest.mock import patch

    consumer = CatalogMessageConsumer(
        broker=AsyncMock(),
        session_factory=mock_session_factory,
    )

    event = ReviewsEnrichFailedEvent(
        payload=ReviewsEnrichFailedPayload(
            job_id="reviews_batch_err_1",
            error_message="ChromaDB upsert timeout",
            s3_key="reviews/raw_1.json",
        )
    )

    expected_uuid = uuid.uuid5(uuid.NAMESPACE_OID, "reviews-enrich-failed:reviews_batch_err_1")

    with patch("app.services.messaging_consumer.BatchLogRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_repo.record_batch_log = AsyncMock()

        await consumer.handle_reviews_enrich_failed(event.model_dump())

    mock_repo.get_by_id.assert_awaited_once_with(expected_uuid)
    mock_repo.record_batch_log.assert_awaited_once_with(
        batch_id=expected_uuid,
        store_key="reviews_enrichment",
        trigger_type="REVIEWS_ENRICH_FAILED",
        status="FAILED",
        error_message="[reviews_batch_err_1] ChromaDB upsert timeout",
    )


@pytest.mark.asyncio
async def test_handle_catalog_ready_event_persists_failed_log_outside_rolled_back_tx():
    from app.models.scraping import ScrapingBatchLog

    tx_events: list[str] = []
    added_rows: list[object] = []

    class _FakeBegin:
        def __init__(self, idx: int) -> None:
            self.idx = idx

        async def __aenter__(self):
            tx_events.append(f"begin:{self.idx}")
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            tx_events.append(f"rollback:{self.idx}" if exc_type else f"commit:{self.idx}")
            return False

    class _FakeSession:
        def __init__(self, idx: int) -> None:
            self.idx = idx
            self.flush = AsyncMock()

        def begin(self):
            return _FakeBegin(self.idx)

        def add(self, obj):
            added_rows.append(obj)

        async def execute(self, *args, **kwargs):
            res = MagicMock()
            # Session 1 inbox claim succeeds; session 2 BatchLog lookup returns None.
            res.scalar_one_or_none.return_value = "claimed-event-id" if self.idx == 1 else None
            return res

    session_counter = 0

    class _FakeSessionCM:
        async def __aenter__(self):
            nonlocal session_counter
            session_counter += 1
            return _FakeSession(session_counter)

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    mock_broker = AsyncMock()
    mock_ingestion = AsyncMock()
    batch_id = uuid.uuid4()
    mock_ingestion.ingest_from_s3.return_value = IngestionResult(
        batch_id=batch_id,
        status="FAILED",
        source="s3://test-bucket/catalogs/bad.json",
        duration_seconds=0.5,
        total_laptops=0,
        new_laptops=0,
        updated_laptops=0,
        offers_created=0,
        offers_updated=0,
        metrics_created=0,
        metrics_updated=0,
        metrics_summary={},
        error_message="NoSuchKey",
    )

    consumer = CatalogMessageConsumer(
        broker=mock_broker,
        session_factory=lambda: _FakeSessionCM(),
        ingestion_service=mock_ingestion,
    )
    event = CatalogReadyEvent(
        payload=CatalogReadyPayload(
            batch_id=str(batch_id),
            s3_bucket="test-bucket",
            s3_key="catalogs/bad.json",
            total_laptops=10,
        )
    )

    with pytest.raises(RuntimeError, match="NoSuchKey"):
        await consumer.handle_catalog_ready_event(event.model_dump())

    # First tx rolled back ingestion; second tx committed FAILED ScrapingBatchLog.
    assert tx_events == ["begin:1", "rollback:1", "begin:2", "commit:2"]
    failed_logs = [row for row in added_rows if isinstance(row, ScrapingBatchLog)]
    assert len(failed_logs) == 1
    assert failed_logs[0].id == batch_id
    assert failed_logs[0].status == "FAILED"
    assert "NoSuchKey" in (failed_logs[0].error_message or "")
