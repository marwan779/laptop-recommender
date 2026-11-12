"""Unit tests verifying catalog handlers reject duplicate events at the inbox gate."""

from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from app.schemas.events import (
    CatalogReadyEvent,
    CatalogReadyPayload,
    PricesCheckedEvent,
    PricesCheckedPayload,
)
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
