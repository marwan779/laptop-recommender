"""Standalone CLI runner for the lightweight price & stock sync cron job.

Invoked periodically by task schedulers (Kubernetes CronJob, Linux crontab,
AWS ECS scheduled tasks) or manually by operators.

Usage:
    # Direct synchronous HTTP run across all stores (unlimited)
    python scripts/run_price_sync_cron.py --no-limit

    # Run for a specific store with a limit
    python scripts/run_price_sync_cron.py --store compumarts --limit 20

    # Asynchronous event-driven run via Transactional Outbox & RabbitMQ
    python scripts/run_price_sync_cron.py --no-limit --mode rabbitmq
"""

import argparse
import asyncio
from pathlib import Path
import sys

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
        help="Maximum stale offers to check per cycle (default: from .env PRICE_SYNC_BATCH_LIMIT, 0 for unlimited)",
    )
    parser.add_argument(
        "--no-limit",
        action="store_true",
        default=False,
        help="Fetch and sync all stale offers without any limit",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["http", "rabbitmq", "outbox"],
        default="http",
        help="Execution mode: 'http' (direct synchronous HTTP call) or 'rabbitmq'/'outbox' (event-driven via Transactional Outbox & RabbitMQ)",
    )
    parser.add_argument(
        "--scraper-url",
        type=str,
        default=None,
        help="Custom scraper-service URL override",
    )

    args = parser.parse_args()

    job = PriceSyncCronJob(scraper_url=args.scraper_url)
    effective_limit = 0 if args.no_limit else args.limit

    if args.mode in ("rabbitmq", "outbox"):
        logger.info(
            "Dispatching price sync cron cycle via Transactional Outbox (RabbitMQ) [store=%s, limit=%s]...",
            args.store,
            "UNLIMITED" if effective_limit == 0 else effective_limit,
        )
        msg_ids = await job.dispatch_once(store_key=args.store, limit=effective_limit)

        print("\n" + "=" * 60)
        print("PRICE SYNC CRON CYCLE DISPATCHED (RABBITMQ OUTBOX)")
        print("=" * 60)
        if not msg_ids:
            print("No stale offers required synchronization.")
        else:
            print(f"Dispatched {len(msg_ids)} outbox batch message(s) to RabbitMQ:")
            for m_id in msg_ids:
                print(f"  - Outbox Message ID: {m_id}")
            print("\nThe running outbox relay and RabbitMQ consumers will process these batches asynchronously.")
        print("=" * 60 + "\n")
    else:
        logger.info(
            "Executing price sync cron cycle via direct HTTP [store=%s, limit=%s]...",
            args.store,
            "UNLIMITED" if effective_limit == 0 else effective_limit,
        )
        summaries = await job.run_once(
            store_key=args.store,
            limit=effective_limit,
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
