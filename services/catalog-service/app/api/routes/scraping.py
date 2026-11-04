import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.scraping import ScrapingBatchLog, StoreScrapingPointer
from app.schemas.scraping import (
    ScrapeTriggerRequest,
    ScrapeTriggerResponse,
    StorePointerResponse,
)
from app.services.scraper_client import ScraperClientService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scraping", tags=["Scraping Coordination"])


@router.post(
    "/trigger",
    response_model=ScrapeTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger full or incremental laptop scraping job",
    description=(
        "Administrative endpoint to trigger the main laptop scraping workflow. "
        "Queries current store watermarks from PostgreSQL, prepares the incremental payload, "
        "and dispatches the job to scraper-service."
    ),
)
async def trigger_scrape_job(
    request: ScrapeTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> ScrapeTriggerResponse:
    """Queue and coordinate a laptop scrape job."""
    service = ScraperClientService()
    return await service.trigger_scrape_job(session=db, request=request)


@router.get(
    "/pointers",
    response_model=list[StorePointerResponse],
    summary="List store scraping watermarks & pointers",
    description="Returns current watermark checkpoints, latest scraped items, and intervals for all stores.",
)
async def get_store_pointers(
    db: AsyncSession = Depends(get_db),
) -> list[StorePointerResponse]:
    """Retrieve all store scraping watermarks."""
    stmt = select(StoreScrapingPointer).order_by(StoreScrapingPointer.store_key)
    result = await db.execute(stmt)
    records = result.scalars().all()
    return [
        StorePointerResponse(
            store_key=r.store_key,
            store_name=r.store_name,
            store_domain=r.store_domain,
            latest_pointers=r.latest_pointers,
            last_scraped_at=r.last_scraped_at,
            total_active_offers=r.total_active_offers,
            scrape_interval_hours=r.scrape_interval_hours,
            is_active=r.is_active,
        )
        for r in records
    ]


@router.get(
    "/logs",
    summary="List recent scraping batch audit logs",
    description="Returns recent audit entries for scraping, ingestion, and price monitor runs.",
)
async def get_scraping_logs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve recent scraping audit logs."""
    stmt = select(ScrapingBatchLog).order_by(desc(ScrapingBatchLog.started_at)).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "store_key": log.store_key,
            "trigger_type": log.trigger_type,
            "status": log.status,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "duration_seconds": float(log.duration_seconds) if log.duration_seconds else None,
            "items_scraped": log.items_scraped,
            "new_laptops_added": log.new_laptops_added,
            "offers_updated": log.offers_updated,
            "error_message": log.error_message,
        }
        for log in logs
    ]
