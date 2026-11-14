import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.scraping_cron import ScrapingCronJob
from app.models.outbox import OutboxMessage
from app.models.scraping import ScrapingBatchLog, StoreScrapingPointer
from app.schemas.events import EventType
from app.services.scraper_client import ScraperClientService


@pytest.mark.asyncio
async def test_scraping_cron_run_once_stages_outbox_success(db_session: AsyncSession):
    store_key = f"cron-scrape-{uuid.uuid4().hex[:8]}"
    pointer = StoreScrapingPointer(
        store_key=store_key,
        store_name="Compumarts",
        store_domain=f"{store_key}.example",
        latest_pointers=["Asus ROG Zephyrus G16"],
        total_active_offers=120,
        scrape_interval_hours=24,
        is_active=True,
    )
    await db_session.merge(pointer)
    await db_session.commit()

    job = ScrapingCronJob(scraper_client=ScraperClientService())
    response = await job.run_once(store_key=store_key, session=db_session)
    await db_session.commit()

    assert response.status == "QUEUED"
    assert store_key in response.stores_targeted
    assert response.pointers_used[store_key] == ["Asus ROG Zephyrus G16"]

    log = await db_session.get(ScrapingBatchLog, uuid.UUID(response.job_id))
    assert log is not None
    assert log.status == "QUEUED"
    assert log.store_key == store_key

    outbox_row = (
        await db_session.execute(
            select(OutboxMessage).where(
                OutboxMessage.event_type == EventType.CATALOG_SCRAPE_COMMAND,
                OutboxMessage.correlation_id == response.job_id,
            )
        )
    ).scalar_one()
    assert outbox_row.routing_key == EventType.CATALOG_SCRAPE_COMMAND
    assert outbox_row.status == "PENDING"


@pytest.mark.asyncio
async def test_scraping_cron_dry_run_skips_http_and_stages_preview(db_session: AsyncSession):
    job = ScrapingCronJob(scraper_client=ScraperClientService())
    response = await job.run_once(store_key="compumarts", session=db_session, dry_run=True)

    assert response.status == "QUEUED"
    assert "outbox" in response.message.lower()
    outbox_row = (
        await db_session.execute(
            select(OutboxMessage).where(OutboxMessage.correlation_id == response.job_id)
        )
    ).scalar_one()
    assert outbox_row.event_type == EventType.CATALOG_SCRAPE_COMMAND
    await db_session.rollback()
