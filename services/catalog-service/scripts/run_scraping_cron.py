"""Standalone CLI runner for the main laptop scraping cron job.

Invoked periodically by an ephemeral Kubernetes CronJob pod or manually by
operators. The job stages a ``catalog.scrape.command`` in the transactional
outbox; the outbox relay then dispatches it to scraper-service.

Usage:
    python scripts/run_scraping_cron.py --dry-run
    python scripts/run_scraping_cron.py --commit
    python scripts/run_scraping_cron.py --commit --store compumarts
    python scripts/run_scraping_cron.py --commit --force-full --level 2
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys

# Ensure catalog-service root is in sys.path
SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.common.logger import configure_logging, get_logger  # noqa: E402
from app.jobs.base_cli import BaseCliJobOptions, BaseCliJobRunner  # noqa: E402
from app.jobs.scraping_cron import ScrapingCronJob  # noqa: E402
from app.schemas.scraping import ScrapeTriggerResponse  # noqa: E402
from app.services.scraper_client import ScraperClientService  # noqa: E402

configure_logging()
logger = get_logger("catalog.scripts.scraping_cron")


@dataclass
class ScrapingCliOptions(BaseCliJobOptions):
    """Domain options for one catalog discovery run."""

    store: str = "all"
    force_full: bool = False
    scraper_url: str | None = None
    level: int | None = None
    send_email: bool | None = None


class ScrapingCronCliRunner(BaseCliJobRunner[ScrapingCliOptions, ScrapeTriggerResponse]):
    """CLI adapter for :class:`ScrapingCronJob`."""

    description = "Stage the main laptop catalog discovery job in the transactional outbox."

    def register_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--store",
            type=str,
            default="all",
            help="Target store ('compumarts', 'elbadr', 'sigma') or 'all' (default: all)",
        )
        parser.add_argument(
            "--force-full",
            action="store_true",
            help="Ignore watermark pointers and perform a full catalog crawl",
        )
        parser.add_argument(
            "--scraper-url",
            type=str,
            default=None,
            help="Custom scraper-service URL override",
        )
        parser.add_argument(
            "--level",
            type=int,
            choices=[1, 2],
            default=None,
            help="Scraping depth override: 1 = summary cards, 2 = deep PDP crawl",
        )
        email_group = parser.add_mutually_exclusive_group()
        email_group.add_argument(
            "--send-email",
            dest="send_email",
            action="store_true",
            default=None,
            help="Send the completion email report",
        )
        email_group.add_argument(
            "--no-send-email",
            dest="send_email",
            action="store_false",
            help="Do not send the completion email report",
        )

    def build_options(self, parsed_args: argparse.Namespace) -> ScrapingCliOptions:
        return ScrapingCliOptions(
            commit=parsed_args.commit,
            dry_run=parsed_args.dry_run,
            store=parsed_args.store,
            force_full=parsed_args.force_full,
            scraper_url=parsed_args.scraper_url,
            level=parsed_args.level,
            send_email=parsed_args.send_email,
        )

    async def execute_job(self, session, options: ScrapingCliOptions) -> ScrapeTriggerResponse:
        job = ScrapingCronJob(
            scraper_client=ScraperClientService(scraper_url=options.scraper_url),
            dispatch_mode="outbox",
        )
        return await job.run_once(
            store_key=options.store,
            force_full_crawl=options.force_full,
            session=session,
            level=options.level,
            send_email=options.send_email,
            dispatch_mode="outbox",
        )

    def render_summary(self, result: ScrapeTriggerResponse, options: ScrapingCliOptions) -> None:
        mode = "COMMITTED" if options.commit else "DRY-RUN (rolled back)"
        print("\n" + "=" * 60, file=self._stdout)
        print("SCRAPING CRON JOB DISPATCH SUMMARY", file=self._stdout)
        print("=" * 60, file=self._stdout)
        print(f"Transaction:     {mode}", file=self._stdout)
        print(f"Job ID:          {result.job_id}", file=self._stdout)
        print(f"Status:          {result.status}", file=self._stdout)
        print(f"Message:         {result.message}", file=self._stdout)
        print(f"Stores Targeted: {', '.join(result.stores_targeted)}", file=self._stdout)
        print(f"Watermarks Sent: {len(result.pointers_used)} stores with pointers", file=self._stdout)
        print("=" * 60 + "\n", file=self._stdout)


# Convenience alias for callers that prefer the shorter job-runner name.
ScrapingCronRunner = ScrapingCronCliRunner


async def main(argv: list[str] | None = None) -> int:
    """Async entry point used by tests and embedding callers."""
    return await ScrapingCronCliRunner().run(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
