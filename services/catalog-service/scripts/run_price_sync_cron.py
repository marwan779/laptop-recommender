"""Standalone CLI runner for the lightweight price & stock sync cron job.

Invoked periodically by task schedulers (Kubernetes CronJob, Linux crontab,
AWS ECS scheduled tasks) or manually by operators.

Usage:
    python scripts/run_price_sync_cron.py
    python scripts/run_price_sync_cron.py --store compumarts --limit 20
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure catalog-service root is in sys.path
SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.common.logger import configure_logging, get_logger  # noqa: E402
from app.jobs.price_sync_cron import PriceSyncCronJob  # noqa: E402

configure_logging()
logger = get_logger("catalog.scripts.price_sync_cron")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trigger the lightweight price and stock monitor sync job.",
    )
    parser.add_argument(
        "--store",
        type=str,
        default=None,
        help="Target store ('compumarts', 'elbadr', 'sigma') or None for all stores",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum stale offers to check per cycle (default: from .env PRICE_SYNC_BATCH_LIMIT)",
    )
    parser.add_argument(
        "--scraper-url",
        type=str,
        default=None,
        help="Custom scraper-service URL override",
    )

    args = parser.parse_args()

    job = PriceSyncCronJob(scraper_url=args.scraper_url)
    logger.info("Initializing price sync cron run...")

    summaries = await job.run_once(
        store_key=args.store,
        limit=args.limit,
    )

    print("\n" + "=" * 60)
    print("PRICE SYNC CRON CYCLE SUMMARY")
    print("=" * 60)
    if not summaries:
        print("No stale offers required synchronization.")
    else:
        for idx, s in enumerate(summaries, start=1):
            print(f"Batch {idx} [{s.store_key}]:")
            print(f"  Processed:       {s.total_processed}")
            print(f"  Updated:         {s.offers_updated}")
            print(f"  Unchanged:       {s.offers_unchanged}")
            print(f"  Price Drops:     {s.price_drops_detected}")
            print(f"  Price Hikes:     {s.price_hikes_detected}")
            print(f"  Out of Stock:    {s.out_of_stock_detected}")
            print(f"  Parents Recalc:  {s.parent_laptops_recalculated}")
            print(f"  Metrics Updated: {s.metrics_recalibrated}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
