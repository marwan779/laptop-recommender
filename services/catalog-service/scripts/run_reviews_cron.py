"""Standalone CLI runner for Stage 2 community review scraping dispatch.

Usage:
    python scripts/run_reviews_cron.py --dry-run --force-all --limit 3 --no-upload-to-s3
    python scripts/run_reviews_cron.py --commit --force-all --limit 3 --no-upload-to-s3 --wait
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.common.logger import configure_logging  # noqa: E402
from app.jobs.base_cli import BaseCliJobOptions, BaseCliJobRunner  # noqa: E402
from app.jobs.batch_watcher import wait_for_reviews_job  # noqa: E402
from app.schemas.scraping import ReviewsTriggerResponse  # noqa: E402
from app.services.review_intelligence_service import ReviewIntelligenceService  # noqa: E402

configure_logging()

DEFAULT_REVIEWS_OUTPUT_DIR = SERVICE_ROOT.parent / "scraper-service" / "scraping results" / "reviews"


@dataclass
class ReviewsCliOptions(BaseCliJobOptions):
    """Domain options for one Stage 2 community review scraping run."""

    force_all: bool = False
    limit: int | None = None
    upload_to_s3: bool = True
    wait: bool = False
    timeout_seconds: float = 600.0
    reviews_dir: Path = DEFAULT_REVIEWS_OUTPUT_DIR


class ReviewsCronCliRunner(BaseCliJobRunner[ReviewsCliOptions, ReviewsTriggerResponse]):
    """CLI adapter for :meth:`ReviewIntelligenceService.dispatch_review_scraping`."""

    description = "Stage a Stage 2 reviews.scrape.command batch in the transactional outbox."

    def register_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--force-all",
            action="store_true",
            default=False,
            help="Include laptops that already have has_reviews=True",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional cap on resolved chassis targets for fast checkpoint smoke testing",
        )
        parser.add_argument(
            "--no-upload-to-s3",
            dest="upload_to_s3",
            action="store_false",
            default=True,
            help="Skip S3 upload, save raw JSON locally, and emit reviews.ready.event with s3_key=None",
        )
        parser.add_argument(
            "--wait",
            action="store_true",
            default=False,
            help="Wait for local reviews artifact / failure audit log and print CLI summary (requires --commit)",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=600.0,
            help="Max seconds to wait when --wait is enabled (default: 600)",
        )
        parser.add_argument(
            "--reviews-dir",
            type=Path,
            default=DEFAULT_REVIEWS_OUTPUT_DIR,
            help="Directory containing local scraper review artifacts when --wait is enabled",
        )

    def build_options(self, parsed_args: argparse.Namespace) -> ReviewsCliOptions:
        return ReviewsCliOptions(
            commit=parsed_args.commit,
            dry_run=parsed_args.dry_run,
            force_all=parsed_args.force_all,
            limit=parsed_args.limit,
            upload_to_s3=parsed_args.upload_to_s3,
            wait=parsed_args.wait,
            timeout_seconds=parsed_args.timeout,
            reviews_dir=parsed_args.reviews_dir,
        )

    async def execute_job(self, session, options: ReviewsCliOptions) -> ReviewsTriggerResponse:
        return await ReviewIntelligenceService().dispatch_review_scraping(
            session=session,
            force_all=options.force_all,
            limit=options.limit,
            upload_to_s3=options.upload_to_s3,
            commit=False,
        )

    def render_summary(self, result: ReviewsTriggerResponse, options: ReviewsCliOptions) -> None:
        mode = "COMMITTED" if options.commit else "DRY-RUN (rolled back)"
        print("\n" + "=" * 60, file=self._stdout)
        print("REVIEWS SCRAPE JOB DISPATCH SUMMARY", file=self._stdout)
        print("=" * 60, file=self._stdout)
        print(f"Transaction:      {mode}", file=self._stdout)
        print(f"Job ID:           {result.job_id}", file=self._stdout)
        print(f"Status:           {result.status}", file=self._stdout)
        print(f"Chassis Queued:   {result.chassis_targets_queued}", file=self._stdout)
        print(f"Laptops Matched:  {result.laptops_matched}", file=self._stdout)
        print(f"Laptops Cloned:   {result.laptops_cloned}", file=self._stdout)
        print(f"Upload To S3:     {options.upload_to_s3}", file=self._stdout)
        print(f"Message:          {result.message}", file=self._stdout)
        print("=" * 60 + "\n", file=self._stdout)

    async def after_commit(self, result: ReviewsTriggerResponse, options: ReviewsCliOptions) -> int | None:
        if not options.wait or result.chassis_targets_queued <= 0:
            return None
        return await wait_for_reviews_job(
            session_factory=self._session_factory,
            job_id=result.job_id,
            stdout=self._stdout,
            reviews_dir=options.reviews_dir,
            timeout_seconds=options.timeout_seconds,
        )


ReviewsCronRunner = ReviewsCronCliRunner


async def main(argv: list[str] | None = None) -> int:
    """Async entry point used by tests and CLI invocations."""
    return await ReviewsCronCliRunner().run(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
