"""Scraper Controller Endpoint (SOLID: Single Responsibility & Dependency Inversion).

Provides an asynchronous HTTP API to trigger scraping workflows in the background
without blocking the HTTP response thread.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.api.deps import get_orchestrator
from app.schemas.orchestrator import ScrapeJobResponse, ScrapeRequest
from app.services.orchestrator import ScrapeOrchestrator

logger = logging.getLogger("scraper.api")
router = APIRouter(prefix="/scrape", tags=["Scraping"])


def _execute_scrape_background(
    orchestrator: ScrapeOrchestrator,
    request: ScrapeRequest,
    job_id: str,
) -> None:
    """Background worker function executing the scraping job asynchronously."""
    logger.info(
        "Starting background scrape job [%s] for target_type='%s', targets=%s, send_email=%s",
        job_id,
        request.target_type,
        request.targets,
        request.send_email,
    )
    print(f"\n[API Worker] Starting background scrape job [{job_id}] ({request.target_type})...")
    try:
        response = orchestrator.execute(request)
        logger.info(
            "Completed background scrape job [%s]: %d targets processed, %d items scraped.",
            job_id,
            response.total_targets,
            response.total_items_scraped,
        )
        print(f"[API Worker] Completed job [{job_id}]: {response.total_items_scraped} items scraped.")
    except Exception as exc:
        logger.error(
            "Background scrape job [%s] failed with exception: %s",
            job_id,
            exc,
            exc_info=True,
        )
        print(f"[API Worker] Error in job [{job_id}]: {exc}")


@router.post(
    "",
    response_model=ScrapeJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger scraping ingestion job",
    description=(
        "Triggers the scraper orchestrator asynchronously in the background. "
        "The request body matches the ScrapeRequest DTO (supports 'brand', 'store', or 'both'). "
        "Returns immediately with HTTP 202 Accepted and a unique job ID without blocking."
    ),
)
async def trigger_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    orchestrator: ScrapeOrchestrator = Depends(get_orchestrator),
) -> ScrapeJobResponse:
    """Enqueue a scrape request and immediately return an acknowledgment."""
    job_id = str(uuid.uuid4())

    # Schedule non-blocking execution
    background_tasks.add_task(
        _execute_scrape_background,
        orchestrator=orchestrator,
        request=request,
        job_id=job_id,
    )

    targets_desc = "all" if request.targets == "all" else f"{len(request.targets)} targets"
    message = (
        f"Scraping job queued successfully for {request.target_type} ({targets_desc}). "
        f"Email notifications: {'enabled' if request.send_email else 'disabled'}."
    )

    return ScrapeJobResponse(
        status="accepted",
        job_id=job_id,
        message=message,
        request=request,
    )
