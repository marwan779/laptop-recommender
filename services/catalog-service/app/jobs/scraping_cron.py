import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.schemas.scraping import ScrapeTriggerRequest, ScrapeTriggerResponse
from app.services.scraper_client import ScraperClientService

logger = logging.getLogger("catalog.jobs.scraping_cron")


class ScrapingCronJob:
    """Stateless one-shot orchestrator for scheduled catalog discovery runs.

    Coordinates between catalog watermarks in PostgreSQL and the
    scraper-service extraction orchestrator. The CLI runner owns the session
    transaction, so this job never commits when a session is supplied.
    """

    def __init__(
        self,
        scraper_client: ScraperClientService | None = None,
        dispatch_mode: str | None = None,
    ) -> None:
        self.client = scraper_client or ScraperClientService()
        self.dispatch_mode = dispatch_mode

    async def run_once(
        self,
        store_key: str = "all",
        force_full_crawl: bool = False,
        session: AsyncSession | None = None,
        http_client: Any | None = None,
        level: int | None = None,
        send_email: bool | None = None,
        dispatch_mode: str | None = None,
        commit: bool = False,
        dry_run: bool = False,
    ) -> ScrapeTriggerResponse:
        """Execute a single scheduled scraping trigger pass.

        Defaults to outbox dispatch for the CLI workflow, while legacy callers
        that explicitly supply an ``httpx`` client keep the HTTP trigger path.
        ``dry_run=True`` forces outbox staging and guarantees no HTTP call.
        """
        resolved_mode = "outbox" if dry_run else (
            dispatch_mode or self.dispatch_mode or ("http" if http_client is not None else "outbox")
        )
        if dry_run:
            commit = False

        request = ScrapeTriggerRequest(
            store_key=store_key,
            level=level if level is not None else settings.scraping_cron_level,
            force_full_crawl=force_full_crawl,
            send_email=send_email if send_email is not None else settings.scraping_cron_send_email,
        )

        logger.info(
            "Executing main laptop scraping cron run: store_key=%s, force_full=%s, level=%d, mode=%s",
            store_key,
            force_full_crawl,
            request.level,
            resolved_mode,
        )

        if session is not None:
            response = await self.client.trigger_scrape_job(
                session=session,
                request=request,
                client=http_client,
                dispatch_mode=resolved_mode,
                dry_run=dry_run,
            )
        else:
            async with AsyncSessionLocal() as sess:
                response = await self.client.trigger_scrape_job(
                    session=sess,
                    request=request,
                    client=http_client,
                    dispatch_mode=resolved_mode,
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
