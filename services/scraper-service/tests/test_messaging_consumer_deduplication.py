"""Unit tests verifying scraper command handler deduplication."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.common.cache import InMemoryCacheProvider
from app.common.messaging.inbox import RedisInboxDeduplicator
from app.schemas.events import (
    CheckPricesCommand,
    CheckPricesPayload,
    ScrapeCatalogCommand,
    ScrapeCatalogPayload,
    ScrapeReviewsCommand,
    ScrapeReviewsPayload,
)
from app.services.messaging_consumer import ScraperMessageConsumer


@pytest.fixture
def mock_broker():
    broker = AsyncMock()
    broker.is_connected = True
    return broker


@pytest.fixture
def inbox():
    cache = InMemoryCacheProvider(default_ttl_seconds=60)
    return RedisInboxDeduplicator(cache, default_ttl_seconds=60)


@pytest.mark.anyio
async def test_duplicate_catalog_command_does_not_run_scraper(mock_broker, inbox):
    orchestrator = MagicMock()
    consumer = ScraperMessageConsumer(
        broker=mock_broker,
        orchestrator=orchestrator,
        inbox=inbox,
    )

    command = ScrapeCatalogCommand(payload=ScrapeCatalogPayload(batch_id="batch-1", targets=["compumarts"]))
    raw = command.model_dump()

    # First delivery is claimed and executed.
    assert await inbox.claim_message(command.event_id, command.event_type) is True
    # Simulate the duplicate: pre-claim then invoke the handler.
    await consumer.handle_catalog_scrape_command(raw)

    orchestrator.execute.assert_not_called()
    mock_broker.publish.assert_not_called()


@pytest.mark.anyio
async def test_duplicate_price_command_does_not_run_monitor(mock_broker, inbox):
    monitor = MagicMock()
    monitor.check_batch_async = AsyncMock()
    consumer = ScraperMessageConsumer(broker=mock_broker, price_monitor=monitor, inbox=inbox)

    command = CheckPricesCommand(payload=CheckPricesPayload(batch_id="batch-p", store_key="compumarts", items=[]))
    assert await inbox.claim_message(command.event_id, command.event_type) is True

    await consumer.handle_check_prices_command(command.model_dump())

    monitor.check_batch_async.assert_not_called()
    mock_broker.publish.assert_not_called()


@pytest.mark.anyio
async def test_duplicate_reviews_command_does_not_run_collector(mock_broker, inbox):
    collector = MagicMock()
    collector.process_reviews_batch = AsyncMock()
    consumer = ScraperMessageConsumer(broker=mock_broker, review_collector=collector, inbox=inbox)

    command = ScrapeReviewsCommand(payload=ScrapeReviewsPayload(job_id="job-1", targets=[]))
    assert await inbox.claim_message(command.event_id, command.event_type) is True

    await consumer.handle_reviews_scrape_command(command.model_dump())

    collector.process_reviews_batch.assert_not_called()


@pytest.mark.anyio
async def test_failed_command_releases_claim_for_retry(mock_broker, inbox):
    monitor = MagicMock()
    monitor.check_batch_async = AsyncMock(side_effect=ConnectionError("store offline"))
    consumer = ScraperMessageConsumer(broker=mock_broker, price_monitor=monitor, inbox=inbox)

    command = CheckPricesCommand(payload=CheckPricesPayload(batch_id="batch-fail", store_key="sigma", items=[]))

    with pytest.raises(ConnectionError):
        await consumer.handle_check_prices_command(command.model_dump())

    # The claim was released so a redelivery can be processed.
    assert await inbox.claim_message(command.event_id, command.event_type) is True


@pytest.mark.anyio
async def test_successful_command_is_marked_completed(mock_broker, inbox):
    collector = MagicMock()
    collector.process_reviews_batch = AsyncMock(return_value="reviews/out.json")
    consumer = ScraperMessageConsumer(broker=mock_broker, review_collector=collector, inbox=inbox)

    command = ScrapeReviewsCommand(payload=ScrapeReviewsPayload(job_id="job-ok", targets=[]))
    await consumer.handle_reviews_scrape_command(command.model_dump())

    assert await inbox.cache.get(f"inbox:{command.event_id}") == b"COMPLETED"
    assert await inbox.claim_message(command.event_id, command.event_type) is False
