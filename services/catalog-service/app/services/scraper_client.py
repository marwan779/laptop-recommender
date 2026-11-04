import logging
import uuid
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.scraping import ScrapingBatchLog, StoreScrapingPointer
from app.schemas.scraping import ScrapeTriggerRequest, ScrapeTriggerResponse

logger = logging.getLogger(__name__)


class ScraperClientService:
    """Client service coordinating scrape job dispatching and watermark injection."""

    def __init__(self, scraper_url: str | None = None) -> None:
        self.scraper_url = (scraper_url or settings.scraper_service_url).rstrip("/")

    async def get_active_store_pointers(
        self,
        session: AsyncSession,
        store_key: str | None = None,
    ) -> list[StoreScrapingPointer]:
        """Fetch active scraping pointers for one or all stores."""
        stmt = select(StoreScrapingPointer).where(StoreScrapingPointer.is_active.is_(True))
        if store_key and store_key != "all":
            stmt = stmt.where(StoreScrapingPointer.store_key == store_key.lower().strip())

        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def trigger_scrape_job(
        self,
        session: AsyncSession,
        request: ScrapeTriggerRequest,
        client: httpx.AsyncClient | None = None,
    ) -> ScrapeTriggerResponse:
        """Coordinate and trigger a scraping ingestion job on scraper-service."""
        pointers = await self.get_active_store_pointers(session, request.store_key)

        targets: list[str] = []
        pointers_map: dict[str, list[str]] = {}

        if request.store_key == "all":
            targets = [p.store_key for p in pointers] if pointers else ["compumarts", "elbadr", "sigma"]
        else:
            targets = [request.store_key.lower().strip()]

        for p in pointers:
            if not request.force_full_crawl and p.latest_pointers:
                pointers_map[p.store_key] = p.latest_pointers

        job_id = str(uuid.uuid4())

        # Collect all watermark pointers into until_model if available
        until_models: list[str] = []
        for ptr_list in pointers_map.values():
            until_models.extend(ptr_list)

        # Log audit record in ScrapingBatchLog for tracking
        batch_log = ScrapingBatchLog(
            id=uuid.UUID(job_id),
            store_key=targets[0] if len(targets) == 1 else "multi-store",
            trigger_type="ADMIN_TRIGGER" if request.force_full_crawl else "CRON",
            status="QUEUED",
            pointers_sent=until_models,
        )
        session.add(batch_log)
        await session.commit()

        # Build payload adhering to scraper-service ScrapeRequest DTO
        scrape_payload = {
            "target_type": "store",
            "targets": targets,
            "level": request.level,
            "until_model": until_models if until_models else None,
            "send_email": request.send_email,
            "upload_to_bucket": True,
        }

        # Dispatch non-blocking request to scraper-service
        endpoint = f"{self.scraper_url}/api/v1/scrape"
        logger.info(
            "Dispatching scrape job [%s] to %s for stores=%s (force_full=%s)",
            job_id,
            endpoint,
            targets,
            request.force_full_crawl,
        )

        try:
            if client:
                resp = await client.post(endpoint, json=scrape_payload, timeout=10.0)
            else:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    resp = await http_client.post(endpoint, json=scrape_payload)

            if resp.status_code in (200, 202):
                batch_log.status = "DISPATCHED"
                await session.commit()
                message = f"Scrape job successfully queued on scraper-service for {targets}."
            else:
                batch_log.status = "DISPATCH_FAILED"
                batch_log.error_message = f"HTTP {resp.status_code}: {resp.text}"
                await session.commit()
                message = f"Scraper-service returned HTTP {resp.status_code}."
        except Exception as exc:
            logger.warning("Could not reach scraper-service at %s: %s", endpoint, exc)
            batch_log.status = "QUEUED_OFFLINE"
            batch_log.error_message = str(exc)
            await session.commit()
            message = f"Job queued in catalog database (scraper-service offline: {exc})."

        return ScrapeTriggerResponse(
            job_id=job_id,
            status=batch_log.status,
            message=message,
            stores_targeted=targets,
            pointers_used=pointers_map,
        )
