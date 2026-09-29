"""Data Transfer Objects for Email Service and Scraper Reports."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

from app.schemas.laptop import utcnow_str
from app.schemas.orchestrator import ScrapeRequest, ScrapeResponse, ScrapeTargetResult


class EmailSendRequest(BaseModel):
    """Generic payload for sending an email."""

    recipients: list[str]
    subject: str
    html_body: str
    text_body: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)


class ScraperFinishedReport(BaseModel):
    """Report payload dispatched immediately after a single scraper finishes."""

    target_type: Literal["brand", "store"]
    target_key: str
    target_name: str
    status: Literal["SUCCESS", "FAILED"]
    mode: str  # "Level 1" or "Level 2"
    scraped_count: int = 0
    total_configurations: int | None = None
    skipped_count: int = 0
    latest_pointers: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    until_model: str | None = None
    error_message: str | None = None
    timestamp: str = Field(default_factory=utcnow_str)

    @classmethod
    def from_target_result(
        cls,
        result: ScrapeTargetResult,
        duration_seconds: float = 0.0,
        until_model: str | None = None,
    ) -> ScraperFinishedReport:
        """Construct a ScraperFinishedReport from a single ScrapeTargetResult."""
        skipped_count = 0
        pointers: list[str] = []
        total_configs = None

        if result.brand_result:
            skipped_count = result.brand_result.total_skipped
            pointers = list(result.brand_result.latest_pointers[:3])
            total_configs = result.brand_result.total_configurations
        elif result.store_result:
            skipped_count = result.store_result.total_skipped
            pointers = list(result.store_result.latest_pointers[:3])

        return cls(
            target_type=result.target_type,
            target_key=result.target_key,
            target_name=result.target_name,
            status="SUCCESS" if result.error is None else "FAILED",
            mode=f"Level {result.level}",
            scraped_count=result.items_scraped,
            total_configurations=total_configs,
            skipped_count=skipped_count,
            latest_pointers=pointers,
            duration_seconds=round(duration_seconds, 1),
            until_model=until_model,
            error_message=result.error,
        )


class TargetSummaryItem(BaseModel):
    """Clean per-target summary item (numbers & pointers only)."""

    target_type: Literal["brand", "store"]
    target_key: str
    target_name: str
    status: Literal["SUCCESS", "FAILED"]
    mode: str  # "Level 1" or "Level 2"
    scraped_count: int = 0
    skipped_count: int = 0
    latest_pointers: list[str] = Field(default_factory=list)
    error_message: str | None = None


class BatchScrapeReport(BaseModel):
    """Consolidated report across all brands or all stores."""

    batch_type: Literal["brand", "store"]
    status: Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
    total_targets: int = 0
    total_scraped: int = 0
    total_skipped: int = 0
    duration_seconds: float = 0.0
    started_at: str
    finished_at: str
    targets: list[TargetSummaryItem] = Field(default_factory=list)

    @classmethod
    def from_scrape_response(
        cls,
        response: ScrapeResponse,
        request: ScrapeRequest,
    ) -> BatchScrapeReport:
        """Factory method to convert an orchestrator response into a clean BatchScrapeReport."""
        target_items: list[TargetSummaryItem] = []
        total_skipped = 0

        for r in response.results:
            is_success = r.error is None
            scraped_count = r.items_scraped
            skipped_count = 0
            pointers: list[str] = []

            if r.brand_result:
                skipped_count = r.brand_result.total_skipped
                pointers = list(r.brand_result.latest_pointers[:3])
            elif r.store_result:
                skipped_count = r.store_result.total_skipped
                pointers = list(r.store_result.latest_pointers[:3])

            total_skipped += skipped_count

            target_items.append(
                TargetSummaryItem(
                    target_type=r.target_type,
                    target_key=r.target_key,
                    target_name=r.target_name,
                    status="SUCCESS" if is_success else "FAILED",
                    mode=f"Level {r.level}",
                    scraped_count=scraped_count,
                    skipped_count=skipped_count,
                    latest_pointers=pointers,
                    error_message=r.error,
                )
            )

        failed_count = sum(1 for t in target_items if t.status == "FAILED")
        if failed_count == 0:
            overall_status = "SUCCESS"
        elif failed_count == len(target_items):
            overall_status = "FAILED"
        else:
            overall_status = "PARTIAL_SUCCESS"

        duration = 0.0
        try:
            start_dt = datetime.fromisoformat(response.started_at)
            end_dt = datetime.fromisoformat(response.finished_at) if response.finished_at else datetime.utcnow()
            duration = max(0.0, (end_dt - start_dt).total_seconds())
        except Exception:
            pass

        return cls(
            batch_type=request.target_type,
            status=overall_status,
            total_targets=len(target_items),
            total_scraped=response.total_items_scraped,
            total_skipped=total_skipped,
            duration_seconds=round(duration, 1),
            started_at=response.started_at,
            finished_at=response.finished_at or datetime.utcnow().isoformat(),
            targets=target_items,
        )
