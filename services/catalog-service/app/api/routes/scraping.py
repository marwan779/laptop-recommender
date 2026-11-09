"""Scraping coordination and Stage 2 review intelligence API routes.

All persistence is delegated to repositories and application services; this
module contains no SQL statements or transaction management.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.batch_log_repository import BatchLogRepository
from app.repositories.pointer_repository import StoreScrapingPointerRepository
from app.schemas.scraping import (
    ReviewsIngestRequest,
    ReviewsIngestResponse,
    ReviewsTriggerRequest,
    ReviewsTriggerResponse,
    ScrapeTriggerRequest,
    ScrapeTriggerResponse,
    StorePointerResponse,
)
from app.services.review_intelligence_service import ReviewIntelligenceService
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
    records = await StoreScrapingPointerRepository(db).list_all_ordered()
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
    logs = await BatchLogRepository(db).list_recent_logs(limit=limit)
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


@router.post(
    "/reviews/trigger",
    response_model=ReviewsTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Dispatch Stage 2 community review scraping",
    description=(
        "Resolves unreviewed catalog laptops into physical chassis targets and enqueues a "
        "`reviews.scrape.command` through the transactional outbox. Use `force_all=true` to "
        "re-resolve the entire catalog even when `has_reviews` is already true."
    ),
)
async def trigger_reviews_scraping(
    request: ReviewsTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> ReviewsTriggerResponse:
    """Queue chassis review scraping targets for scraper-service."""
    service = ReviewIntelligenceService()
    return await service.dispatch_review_scraping(session=db, force_all=request.force_all)


@router.post(
    "/reviews/ingest",
    response_model=ReviewsIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest enriched reviews into ChromaDB and PostgreSQL",
    description=(
        "Loads an enriched chassis reviews artifact from local disk or S3, embeds bilingual "
        "pro/con/context vectors into ChromaDB, and persists `community_nlp_score`, the 5 aspect "
        "scores, evidence counts, bilingual pros/cons, and reviewed flags into PostgreSQL."
    ),
)
async def ingest_reviews(
    request: ReviewsIngestRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
) -> ReviewsIngestResponse:
    """Run Stage 2 review intelligence ingestion."""
    chroma_service = getattr(http_request.app.state, "chroma_reviews", None)
    service = ReviewIntelligenceService(chroma_service=chroma_service)

    try:
        if request.from_s3:
            result = await service.ingest_from_s3(db, request.source_path)
        else:
            result = await service.ingest_from_file(db, request.source_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ReviewsIngestResponse(
        status=result.status,
        chassis_processed=result.chassis_processed,
        chroma_documents_upserted=result.chroma_documents_upserted,
        sql_laptops_updated=result.sql_laptops_updated,
        duration_seconds=result.duration_seconds,
    )
