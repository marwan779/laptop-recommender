import asyncio
import logging
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.schemas.scraping import ScrapeTriggerRequest, ScrapeTriggerResponse
from app.services.scraper_client import ScraperClientService

logger = logging.getLogger("catalog.jobs.scraping_cron")


class ScrapingCronJob:
    """Manages scheduled weekly incremental laptop discovery runs.

    Coordinates between catalog watermarks in PostgreSQL and the
    scraper-service 8-layer extraction orchestrator.
    """

    def __init__(self, scraper_client: ScraperClientService | None = None) -> None:
        self.client = scraper_client or ScraperClientService()
        self._task: asyncio.Task | None = None
        self._is_running: bool = False

    async def run_once(
        self,
        store_key: str = "all",
        force_full_crawl: bool = False,
        session: AsyncSession | None = None,
        http_client: Any | None = None,
    ) -> ScrapeTriggerResponse:
        """Execute a single scheduled scraping trigger pass."""
        logger.info(
            "Executing main laptop scraping cron run: store_key=%s, force_full=%s, level=%d",
            store_key,
            force_full_crawl,
            settings.scraping_cron_level,
        )

        request = ScrapeTriggerRequest(
            store_key=store_key,
            level=settings.scraping_cron_level,
            force_full_crawl=force_full_crawl,
            send_email=settings.scraping_cron_send_email,
        )

        if session is not None:
            response = await self.client.trigger_scrape_job(
                session=session,
                request=request,
                client=http_client,
            )
        else:
            async with AsyncSessionLocal() as sess:
                response = await self.client.trigger_scrape_job(
                    session=sess,
                    request=request,
                    client=http_client,
                )

        logger.info(
            "Scraping cron job triggered successfully: job_id=%s, status=%s, stores=%s",
            response.job_id,
            response.status,
            response.stores_targeted,
        )
        return response

    async def _scheduler_loop(self) -> None:
        """Periodic background execution loop."""
        interval_seconds = max(3600, settings.scraping_cron_interval_hours * 3600)
        logger.info(
            "Starting scraping cron scheduler loop (interval: %d hours / %d seconds)",
            settings.scraping_cron_interval_hours,
            interval_seconds,
        )

        self._is_running = True
        try:
            while self._is_running:
                await asyncio.sleep(interval_seconds)
                try:
                    await self.run_once(store_key="all", force_full_crawl=False)
                except Exception as exc:
                    logger.error("Error occurred in scraping cron loop: %s", exc, exc_info=True)
        except asyncio.CancelledError:
            logger.info("Scraping cron scheduler loop received cancellation signal. Stopping.")
        finally:
            self._is_running = False

    def start(self) -> asyncio.Task | None:
        """Start the background scheduler task if enabled in configuration."""
        if not settings.enable_scraping_cron:
            logger.info("Scraping cron job is disabled (enable_scraping_cron=False).")
            return None

        if self._task and not self._task.done():
            logger.warning("Scraping cron task is already running.")
            return self._task

        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._scheduler_loop(), name="scraping-cron-scheduler")
        return self._task

    async def stop(self) -> None:
        """Cancel and await the background scheduler task."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Scraping cron scheduler stopped.")


# Singleton instance
scraping_cron = ScrapingCronJob()
