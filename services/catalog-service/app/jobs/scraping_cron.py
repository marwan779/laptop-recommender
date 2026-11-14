import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.schemas.scraping import ScrapeTriggerRequest, ScrapeTriggerResponse
from app.services.scraper_client import ScraperClientService

logger = logging.getLogger("catalog.jobs.scraping_cron")


class ScrapingCronJob:
    """Stateless one-shot orchestrator for scheduled catalog discovery runs.

    Coordinates between catalog watermarks in PostgreSQL and the
    transactional outbox to enqueue scraper-service discovery commands.
    The CLI runner owns the session transaction, so this job never commits
    when a session is supplied.
    """

    def __init__(
        self,
        scraper_client: ScraperClientService | None = None,
    ) -> None:
        self.client = scraper_client or ScraperClientService()

    async def run_once(
        self,
        store_key: str = "all",
        force_full_crawl: bool = False,
        session: AsyncSession | None = None,
        level: int | None = None,
        send_email: bool | None = None,
        commit: bool = False,
        dry_run: bool = False,
    ) -> ScrapeTriggerResponse:
        """Stage a scheduled scraping trigger pass in the transactional outbox."""
        if dry_run:
            commit = False

        request = ScrapeTriggerRequest(
            store_key=store_key,
            level=level if level is not None else settings.scraping_cron_level,
            force_full_crawl=force_full_crawl,
            send_email=send_email if send_email is not None else settings.scraping_cron_send_email,
        )

        logger.info(
            "Executing main laptop scraping cron run: store_key=%s, force_full=%s, level=%d, mode=outbox",
            store_key,
            force_full_crawl,
            request.level,
        )

        if session is not None:
            response = await self.client.trigger_scrape_job(
                session=session,
                request=request,
                dispatch_mode="outbox",
                dry_run=dry_run,
            )
        else:
            async with AsyncSessionLocal() as sess:
                response = await self.client.trigger_scrape_job(
                    session=sess,
                    request=request,
                    dispatch_mode="outbox",
                    dry_run=dry_run,
                )
                if commit:
                    await sess.commit()
                else:
                    await sess.rollback()

        logger.info(
            "Scraping cron job triggered successfully: job_id=%s, status=%s, stores=%s",
            response.job_id,
            response.status,
            response.stores_targeted,
        )
        return response


# Backwards-compatible module-level instance for callers/tests that import it.
scraping_cron = ScrapingCronJob()
