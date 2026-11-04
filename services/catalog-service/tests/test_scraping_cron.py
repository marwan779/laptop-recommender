import asyncio
import uuid
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.jobs.scraping_cron import ScrapingCronJob
from app.models.scraping import ScrapingBatchLog, StoreScrapingPointer
from app.services.scraper_client import ScraperClientService


@pytest.mark.asyncio
async def test_scraping_cron_run_once_success(db_session: AsyncSession):
    # Seed pointer
    pointer = StoreScrapingPointer(
        store_key="compumarts",
        store_name="Compumarts",
        store_domain="compumarts.com",
        latest_pointers=["Asus ROG Zephyrus G16"],
        total_active_offers=120,
        scrape_interval_hours=24,
        is_active=True,
    )
    await db_session.merge(pointer)
    await db_session.commit()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        assert body["targets"] == ["compumarts"]
        assert body["until_model"] == ["Asus ROG Zephyrus G16"]
        return httpx.Response(202, json={"status": "accepted", "job_id": str(uuid.uuid4())})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    scraper_client = ScraperClientService()
    job = ScrapingCronJob(scraper_client=scraper_client)

    response = await job.run_once(store_key="compumarts", session=db_session, http_client=mock_client)

    assert response.status == "DISPATCHED"
    assert "compumarts" in response.stores_targeted
    assert response.pointers_used["compumarts"] == ["Asus ROG Zephyrus G16"]

    # Verify ScrapingBatchLog audit entry
    log = await db_session.get(ScrapingBatchLog, uuid.UUID(response.job_id))
    assert log is not None
    assert log.status == "DISPATCHED"
    assert log.store_key == "compumarts"


@pytest.mark.asyncio
async def test_scraping_cron_disabled_by_default():
    job = ScrapingCronJob()
    # By default in settings, enable_scraping_cron is False
    assert settings.enable_scraping_cron is False
    task = job.start()
    assert task is None


@pytest.mark.asyncio
async def test_scraping_cron_lifecycle_start_and_stop():
    job = ScrapingCronJob()

    # Temporarily enable cron
    original_setting = settings.enable_scraping_cron
    settings.enable_scraping_cron = True
    try:
        task = job.start()
        assert task is not None
        assert not task.done()

        # Stop should cleanly cancel and await
        await job.stop()
        assert task.done()
        assert job._task is None
    finally:
        settings.enable_scraping_cron = original_setting


@pytest.mark.asyncio
async def test_scraping_cron_offline_resilience(db_session: AsyncSession):
    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by scraper-service")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(failing_handler))
    scraper_client = ScraperClientService()
    job = ScrapingCronJob(scraper_client=scraper_client)

    response = await job.run_once(store_key="compumarts", session=db_session, http_client=mock_client)

    assert response.status == "QUEUED_OFFLINE"
    assert "offline" in response.message.lower()

    # Verify audit entry marked as offline
    log = await db_session.get(ScrapingBatchLog, uuid.UUID(response.job_id))
    assert log is not None
    assert log.status == "QUEUED_OFFLINE"
    assert "Connection refused" in (log.error_message or "")
