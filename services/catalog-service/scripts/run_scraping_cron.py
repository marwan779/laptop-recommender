"""Standalone CLI runner for the main laptop scraping cron job.

Invoked periodically by task schedulers (Kubernetes CronJob, Linux crontab,
AWS ECS scheduled tasks) or manually by operators.

Usage:
    python scripts/run_scraping_cron.py
    python scripts/run_scraping_cron.py --store compumarts
    python scripts/run_scraping_cron.py --force-full
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure catalog-service root is in sys.path
SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.common.logger import configure_logging, get_logger  # noqa: E402
from app.jobs.scraping_cron import ScrapingCronJob  # noqa: E402
from app.services.scraper_client import ScraperClientService  # noqa: E402

configure_logging()
logger = get_logger("catalog.scripts.scraping_cron")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trigger the main laptop scraping ingestion cron job.",
    )
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

    args = parser.parse_args()

    client = ScraperClientService(scraper_url=args.scraper_url)
    job = ScrapingCronJob(scraper_client=client)

    logger.info("Initializing main scraping cron run...")
    response = await job.run_once(
        store_key=args.store,
        force_full_crawl=args.force_full,
    )

    print("\n" + "=" * 60)
    print("SCRAPING CRON JOB DISPATCH SUMMARY")
    print("=" * 60)
    print(f"Job ID:          {response.job_id}")
    print(f"Status:          {response.status}")
    print(f"Message:         {response.message}")
    print(f"Stores Targeted: {', '.join(response.stores_targeted)}")
    print(f"Watermarks Sent: {len(response.pointers_used)} stores with pointers")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
