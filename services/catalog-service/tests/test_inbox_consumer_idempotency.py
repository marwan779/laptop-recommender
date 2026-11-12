"""Unit tests verifying catalog handlers reject duplicate events at the inbox gate."""

from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbox import InboxMessage
from app.schemas.events import (
    CatalogReadyEvent,
    CatalogReadyPayload,
    CatalogScrapeFailedEvent,
    CatalogScrapeFailedPayload,
    PricesCheckedEvent,
    PricesCheckedPayload,
    ReviewsReadyEvent,
    ReviewsReadyPayload,
)
from app.schemas.price_sync import PriceSyncSummary
from app.services.messaging_consumer import CatalogMessageConsumer


def _session_factory(session):
    class FakeBeginCM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    class FakeSessionCM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    session.begin = MagicMock(return_value=FakeBeginCM())
    session.add = MagicMock()
    return lambda: FakeSessionCM()


def _duplicate_result():
    """Result emulating INSERT ... ON CONFLICT DO NOTHING returning no row."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    return result


@pytest.mark.asyncio
async def test_duplicate_catalog_ready_event_skips_ingestion():
    session = AsyncMock()
    session.execute.return_value = _duplicate_result()
    ingestion = AsyncMock()
    consumer = CatalogMessageConsumer(
        broker=AsyncMock(),
        session_factory=_session_factory(session),
        ingestion_service=ingestion,
    )

    event = CatalogReadyEvent(
        payload=CatalogReadyPayload(
            batch_id=str(uuid.uuid4()),
            s3_bucket="bucket",
            s3_key="catalogs/catalog.json",
            total_laptops=10,
        )
    )

    await consumer.handle_catalog_ready_event(event.model_dump())

    ingestion.ingest_from_s3.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_prices_checked_event_skips_price_sync():
    session = AsyncMock()
    session.execute.return_value = _duplicate_result()
    price_sync = AsyncMock()
    consumer = CatalogMessageConsumer(
        broker=AsyncMock(),
        session_factory=_session_factory(session),
        price_sync_service=price_sync,
    )

    event = PricesCheckedEvent(
        payload=PricesCheckedPayload(
            batch_id="batch-dup",
            store_key="compumarts",
            total_items=5,
            changed_items_count=1,
        )
    )

    await consumer.handle_prices_checked_event(event.model_dump())

    price_sync.apply_batch_results.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_catalog_scrape_failed_event_skips_batch_log_update(monkeypatch):
    session = AsyncMock()
    session.execute.return_value = _duplicate_result()

    batch_log_repo = MagicMock()
    monkeypatch.setattr(
        "app.services.messaging_consumer.BatchLogRepository",
        batch_log_repo,
    )

    consumer = CatalogMessageConsumer(
        broker=AsyncMock(),
        session_factory=_session_factory(session),
    )

    event = CatalogScrapeFailedEvent(
        payload=CatalogScrapeFailedPayload(
            batch_id=str(uuid.uuid4()),
            error_message="store unreachable",
        )
    )

    await consumer.handle_catalog_scrape_failed(event.model_dump())

    # Duplicate delivery must not construct or mutate the batch log repository.
    batch_log_repo.assert_not_called()
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_reviews_ready_event_skips_review_ingestion():
    session = AsyncMock()
    session.execute.return_value = _duplicate_result()
    review_service = AsyncMock()

    consumer = CatalogMessageConsumer(
        broker=AsyncMock(),
        session_factory=_session_factory(session),
        review_intelligence_service=review_service,
    )

    event = ReviewsReadyEvent(
        payload=ReviewsReadyPayload(
            job_id="job-dup",
            total_laptops=1,
            total_snippets=10,
            s3_key="reviews/enriched.json",
        )
    )

    await consumer.handle_reviews_ready_event(event.model_dump())

    review_service.ingest_from_s3.assert_not_called()
    session.execute.assert_awaited_once()


class _NonClosingSessionContext:
    """Yield an existing test session without closing it."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


@pytest.mark.asyncio
async def test_handler_failure_rolls_back_inbox_claim_for_redelivery(db_session: AsyncSession):
    session_factory = lambda: _NonClosingSessionContext(db_session)  # noqa: E731

    failing_service = AsyncMock()
    failing_service.apply_batch_results.side_effect = RuntimeError("domain write failed")
    failing_consumer = CatalogMessageConsumer(
        broker=AsyncMock(),
        session_factory=session_factory,
        price_sync_service=failing_service,
    )

    event = PricesCheckedEvent(
        payload=PricesCheckedPayload(
            batch_id="batch-rollback",
            store_key="compumarts",
            total_items=1,
            changed_items_count=0,
        )
    )

    with pytest.raises(RuntimeError, match="domain write failed"):
        await failing_consumer.handle_prices_checked_event(event.model_dump())

    async def _inbox_row():
        result = await db_session.execute(
            select(InboxMessage).where(InboxMessage.message_id == event.event_id)
        )
        return result.scalar_one_or_none()

    # The claim was rolled back atomically with the failed business work.
    assert await _inbox_row() is None

    # End the implicit read transaction before simulating a fresh redelivery.
    await db_session.rollback()

    # A redelivery can now claim and process the same event id successfully.
    succeeding_service = AsyncMock()
    succeeding_service.apply_batch_results.return_value = PriceSyncSummary(
        batch_id="batch-rollback",
        store_key="compumarts",
        total_processed=1,
        offers_updated=0,
    )
    succeeding_consumer = CatalogMessageConsumer(
        broker=AsyncMock(),
        session_factory=session_factory,
        price_sync_service=succeeding_service,
    )

    await succeeding_consumer.handle_prices_checked_event(event.model_dump())

    assert await _inbox_row() is not None
