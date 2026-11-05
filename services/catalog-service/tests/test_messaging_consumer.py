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
    ReviewsReadyEvent,
    ReviewsReadyPayload,
)
from app.schemas.price_sync import PriceChangeType, PriceCheckItemResult, PriceSyncSummary
from app.services.catalog_ingestion_service import IngestionResult
from app.services.messaging_consumer import CatalogMessageConsumer


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.begin = MagicMock()

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

    assert mock_broker.subscribe.call_count == 4
    subscriptions = {
        call.kwargs["queue_name"]: call.kwargs["routing_key"] for call in mock_broker.subscribe.call_args_list
    }

    assert subscriptions["catalog.ready.jobs"] == EventType.CATALOG_READY_EVENT
    assert subscriptions["catalog.scrape.failed.jobs"] == EventType.CATALOG_SCRAPE_FAILED_EVENT
    assert subscriptions["catalog.prices.checked.jobs"] == EventType.PRICES_CHECKED_EVENT
    assert subscriptions["catalog.reviews.ready.jobs"] == EventType.REVIEWS_READY_EVENT


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


@pytest.mark.asyncio
async def test_handle_reviews_ready_event():
    mock_broker = AsyncMock()
    consumer = CatalogMessageConsumer(broker=mock_broker)

    event = ReviewsReadyEvent(
        payload=ReviewsReadyPayload(
            job_id="job-rec-1",
            total_laptops=1,
            total_snippets=0,
            results=[],
        )
    )

    # Should not raise
    await consumer.handle_reviews_ready_event(event.model_dump())
