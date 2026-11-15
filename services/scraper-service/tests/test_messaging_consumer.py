"""Unit tests for ScraperMessageConsumer dispatching and execution."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.price_monitor.models import (
    PriceChangeType,
    PriceCheckBatchResponse,
    PriceCheckItemResult,
)
from app.schemas.events import (
    CatalogReadyEvent,
    CatalogScrapeFailedEvent,
    CheckPricesCommand,
    CheckPricesPayload,
    EventType,
    PricesCheckedEvent,
    ScrapeCatalogCommand,
    ScrapeCatalogPayload,
    ScrapeReviewsCommand,
    ScrapeReviewsPayload,
)
from app.schemas.laptop import StoreCatalogResult
from app.schemas.orchestrator import ScrapeResponse, ScrapeTargetResult
from app.services.messaging_consumer import ScraperMessageConsumer


@pytest.fixture
def mock_broker():
    broker = AsyncMock()
    broker.is_connected = True
    return broker


@pytest.fixture
def mock_orchestrator():
    orch = MagicMock()
    orch.storage_service = MagicMock()
    orch.storage_service.bucket_name = "test-catalog-bucket"
    return orch


@pytest.fixture
def mock_price_monitor():
    pm = MagicMock()
    pm.check_batch_async = AsyncMock()
    return pm


@pytest.mark.anyio
async def test_consumer_start_listening(mock_broker, mock_orchestrator, mock_price_monitor):
    consumer = ScraperMessageConsumer(
        broker=mock_broker,
        orchestrator=mock_orchestrator,
        price_monitor=mock_price_monitor,
    )

    await consumer.start_listening()

    assert mock_broker.subscribe.call_count == 3
    calls = mock_broker.subscribe.call_args_list

    # Catalog queue
    assert calls[0].kwargs["queue_name"] == "scraper.catalog.jobs"
    assert calls[0].kwargs["routing_key"] == EventType.CATALOG_SCRAPE_COMMAND
    assert calls[0].kwargs["prefetch_count"] == 1

    # Price queue
    assert calls[1].kwargs["queue_name"] == "scraper.price.jobs"
    assert calls[1].kwargs["routing_key"] == EventType.PRICES_CHECK_COMMAND
    assert calls[1].kwargs["prefetch_count"] == 5

    # Reviews queue
    assert calls[2].kwargs["queue_name"] == "scraper.reviews.jobs"
    assert calls[2].kwargs["routing_key"] == EventType.REVIEWS_SCRAPE_COMMAND


@pytest.mark.anyio
async def test_handle_catalog_scrape_command_success(mock_broker, mock_orchestrator):
    consumer = ScraperMessageConsumer(
        broker=mock_broker,
        orchestrator=mock_orchestrator,
    )

    mock_target = ScrapeTargetResult(
        target_type="store",
        target_key="compumarts",
        target_name="Compumarts",
        level=2,
        items_scraped=10,
        store_result=StoreCatalogResult(
            store_key="compumarts",
            store_name="Compumarts",
            store_domain="compumarts.com",
            total_products=1,
            latest_pointers=["Legion 5"],
        ),
    )
    mock_orchestrator.execute.return_value = ScrapeResponse(
        results=[mock_target],
        total_targets=1,
        total_items_scraped=10,
        unified_storage_key="catalogs/catalog_batch-seed-001.json",
        unified_storage_bucket="test-catalog-bucket",
    )

    cmd = ScrapeCatalogCommand(
        payload=ScrapeCatalogPayload(
            batch_id="batch-seed-001",
            targets=["compumarts"],
            level=2,
        )
    )

    await consumer.handle_catalog_scrape_command(cmd.model_dump())

    mock_orchestrator.execute.assert_called_once()
    mock_broker.publish.assert_called_once()

    published_call = mock_broker.publish.call_args
    assert published_call.kwargs["routing_key"] == EventType.CATALOG_READY_EVENT
    ready_evt: CatalogReadyEvent = published_call.kwargs["message"]
    assert ready_evt.payload.batch_id == "batch-seed-001"
    assert ready_evt.payload.s3_key == "catalogs/catalog_batch-seed-001.json"
    assert ready_evt.payload.s3_bucket == "test-catalog-bucket"
    assert ready_evt.payload.total_laptops == 10
    assert ready_evt.payload.pointers_found == {"compumarts": ["Legion 5"]}


@pytest.mark.anyio
async def test_handle_catalog_scrape_command_failure(mock_broker, mock_orchestrator):
    consumer = ScraperMessageConsumer(
        broker=mock_broker,
        orchestrator=mock_orchestrator,
    )
    mock_orchestrator.execute.side_effect = ConnectionResetError("Target store refused connection")

    cmd = ScrapeCatalogCommand(
        payload=ScrapeCatalogPayload(
            batch_id="batch-fail-001",
            targets=["sigma"],
        )
    )

    with pytest.raises(ConnectionResetError):
        await consumer.handle_catalog_scrape_command(cmd.model_dump())

    # Verify failure event was published before raising
    mock_broker.publish.assert_called_once()
    published_call = mock_broker.publish.call_args
    assert published_call.kwargs["routing_key"] == EventType.CATALOG_SCRAPE_FAILED_EVENT
    failed_evt: CatalogScrapeFailedEvent = published_call.kwargs["message"]
    assert failed_evt.payload.batch_id == "batch-fail-001"
    assert "Target store refused connection" in failed_evt.payload.error_message


@pytest.mark.anyio
async def test_handle_check_prices_command(mock_broker, mock_price_monitor):
    consumer = ScraperMessageConsumer(
        broker=mock_broker,
        price_monitor=mock_price_monitor,
    )

    mock_price_monitor.check_batch_async.return_value = PriceCheckBatchResponse(
        batch_id="batch-price-001",
        store_key="compumarts",
        total_items=1,
        changed_items_count=1,
        price_drops_count=1,
        duration_seconds=1.2,
        results=[
            PriceCheckItemResult(
                offer_id="off-10",
                laptop_id="lap-20",
                product_url="https://compumarts.com/loq",
                old_price_egp=35000.0,
                new_price_egp=33000.0,
                old_in_stock=True,
                new_in_stock=True,
                has_changed=True,
                change_type=PriceChangeType.PRICE_DROP,
            )
        ],
    )

    cmd = CheckPricesCommand(
        payload=CheckPricesPayload(
            batch_id="batch-price-001",
            store_key="compumarts",
            items=[],
        )
    )

    await consumer.handle_check_prices_command(cmd.model_dump())

    mock_price_monitor.check_batch_async.assert_called_once()
    mock_broker.publish.assert_called_once()
    published_call = mock_broker.publish.call_args
    assert published_call.kwargs["routing_key"] == EventType.PRICES_CHECKED_EVENT
    price_evt: PricesCheckedEvent = published_call.kwargs["message"]
    assert price_evt.payload.batch_id == "batch-price-001"
    assert price_evt.payload.price_drops_count == 1
    assert price_evt.payload.results[0].new_price_egp == 33000.0


@pytest.mark.anyio
async def test_handle_reviews_scrape_command(mock_broker):
    collector = MagicMock()
    collector.process_reviews_batch = AsyncMock(return_value="reviews/raw_chassis_reviews_job-rec-001.json")
    consumer = ScraperMessageConsumer(broker=mock_broker, review_collector=collector)

    cmd = ScrapeReviewsCommand(
        payload=ScrapeReviewsPayload(
            job_id="job-rec-001",
            targets=[],
        )
    )

    await consumer.handle_reviews_scrape_command(cmd.model_dump())

    collector.process_reviews_batch.assert_awaited_once()
    delegated: ScrapeReviewsCommand = collector.process_reviews_batch.await_args.args[0]
    assert delegated.payload.job_id == "job-rec-001"


@pytest.mark.anyio
async def test_handle_catalog_scrape_command_emits_failed_when_missing_s3_key(mock_broker, mock_orchestrator):
    consumer = ScraperMessageConsumer(
        broker=mock_broker,
        orchestrator=mock_orchestrator,
    )
    mock_target = ScrapeTargetResult(
        target_type="store",
        target_key="compumarts",
        target_name="Compumarts",
        level=2,
        items_scraped=0,
        error="HTTP 503",
    )
    mock_orchestrator.execute.return_value = ScrapeResponse(
        results=[mock_target],
        total_targets=1,
        total_items_scraped=0,
        unified_storage_key=None,
        unified_error="S3 upload failed: NoCredentialsError",
    )

    cmd = ScrapeCatalogCommand(
        payload=ScrapeCatalogPayload(
            batch_id="batch-missing-s3",
            targets=["compumarts"],
            level=2,
            upload_to_bucket=True,
        )
    )

    with pytest.raises(RuntimeError):
        await consumer.handle_catalog_scrape_command(cmd.model_dump())

    mock_broker.publish.assert_called_once()
    assert mock_broker.publish.call_args.kwargs["routing_key"] == EventType.CATALOG_SCRAPE_FAILED_EVENT
    failed_evt: CatalogScrapeFailedEvent = mock_broker.publish.call_args.kwargs["message"]
    assert failed_evt.payload.batch_id == "batch-missing-s3"


@pytest.mark.anyio
async def test_handle_catalog_scrape_command_uses_unified_total_laptops(mock_broker, mock_orchestrator):
    consumer = ScraperMessageConsumer(
        broker=mock_broker,
        orchestrator=mock_orchestrator,
    )
    mock_target = ScrapeTargetResult(
        target_type="store",
        target_key="compumarts",
        target_name="Compumarts",
        level=2,
        items_scraped=12,
        store_result=StoreCatalogResult(
            store_key="compumarts",
            store_name="Compumarts",
            store_domain="compumarts.com",
            total_products=12,
            latest_pointers=["LOQ 15"],
        ),
    )
    mock_orchestrator.execute.return_value = ScrapeResponse(
        results=[mock_target],
        total_targets=1,
        total_items_scraped=12,
        unified_storage_key="catalogs/catalog_batch-uniq.json",
        unified_storage_bucket="test-catalog-bucket",
        unified_total_laptops=7,
    )

    cmd = ScrapeCatalogCommand(
        payload=ScrapeCatalogPayload(
            batch_id="batch-uniq",
            targets=["compumarts"],
            level=2,
        )
    )

    await consumer.handle_catalog_scrape_command(cmd.model_dump())

    ready_evt: CatalogReadyEvent = mock_broker.publish.call_args.kwargs["message"]
    assert ready_evt.payload.total_laptops == 7


def test_orchestrator_skips_s3_upload_and_records_error_when_unified_catalog_empty(tmp_path):
    from unittest.mock import patch

    from app.common.storage.base import IObjectStorageService
    from app.schemas.laptop import RetailerProduct
    from app.schemas.orchestrator import ScrapeRequest
    from app.services.orchestrator import ScrapeOrchestrator

    mock_storage = MagicMock(spec=IObjectStorageService)
    mock_storage.bucket_name = "test-catalog-bucket"
    orchestrator = ScrapeOrchestrator(
        email_service=MagicMock(),
        no_audit=True,
        ai_type="none",
        storage_service=mock_storage,
        upload_to_bucket=True,
    )

    empty_unified = MagicMock()
    empty_unified.total_unique_laptops = 0
    empty_unified.stores_included = []
    empty_unified.model_dump.return_value = {"total_unique_laptops": 0, "laptops": []}

    sample_product = RetailerProduct(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title="Test Laptop",
        product_url="https://compumarts.com/p/1",
        price_egp=40000.0,
    )

    req = ScrapeRequest(
        target_type="store",
        targets=["compumarts"],
        level=2,
        output_dir=str(tmp_path),
        upload_to_bucket=True,
        send_email=False,
        batch_id="batch-empty-unified",
    )

    with (
        patch("app.services.orchestrator.get_store_scraper") as mock_get_store,
        patch("app.matching.combiner.CatalogCombiner.combine_catalogs", return_value=empty_unified),
        patch("app.pipeline.icecat.enricher.IcecatCatalogEnricher.enrich_catalog", return_value=empty_unified),
    ):
        mock_scraper = MagicMock()
        mock_scraper.store_name = "Compumarts"
        mock_scraper.store_key = "compumarts"
        mock_scraper.base_domain = "compumarts.com"
        mock_scraper.scrape_catalog.return_value = [sample_product]
        mock_scraper.skipped_laptops = []
        mock_get_store.return_value = mock_scraper

        res = orchestrator.execute(req)

    uploaded_keys = [call.kwargs.get("object_key") for call in mock_storage.upload_json.call_args_list]
    assert all(not str(k).startswith("catalogs/") for k in uploaded_keys)
    assert res.unified_storage_key is None
    assert res.unified_total_laptops == 0
    assert res.unified_error is not None
