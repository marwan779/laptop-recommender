"""Standalone CLI runner for the lightweight price and stock sync cron job.

Invoked periodically by an ephemeral Kubernetes CronJob pod or manually by
operators. Stages ``prices.check.command`` batches in the transactional outbox
so the pod can exit immediately and the outbox relay dispatches them to
RabbitMQ.

Usage:
    python scripts/run_price_sync_cron.py --dry-run
    python scripts/run_price_sync_cron.py --commit --no-limit
    python scripts/run_price_sync_cron.py --commit --store compumarts --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import sys

# Ensure catalog-service root is in sys.path
SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.common.logger import configure_logging, get_logger  # noqa: E402
from app.jobs.base_cli import BaseCliJobOptions, BaseCliJobRunner  # noqa: E402
from app.jobs.price_sync_cron import PriceSyncCronJob  # noqa: E402

configure_logging()
logger = get_logger("catalog.scripts.price_sync_cron")


@dataclass
class PriceSyncCliOptions(BaseCliJobOptions):
    """Domain options for one price and availability monitoring run."""

    store: str | None = None
    limit: int | None = None
    no_limit: bool = False


@dataclass
class PriceSyncCliResult:
    """Structured terminal summary payload for outbox dispatch."""

    store: str | None = None
    message_ids: list[str] = field(default_factory=list)


class PriceSyncCronCliRunner(BaseCliJobRunner[PriceSyncCliOptions, PriceSyncCliResult]):
    """CLI adapter for :class:`PriceSyncCronJob`."""

    description = "Stage the lightweight price and stock monitor sync batches in the outbox."

    def register_arguments(self, parser: argparse.ArgumentParser) -> None:
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
            help="Maximum stale offers to check (default: PRICE_SYNC_BATCH_LIMIT, 0 for unlimited)",
        )
        parser.add_argument(
            "--no-limit",
            action="store_true",
            default=False,
            help="Fetch and sync all stale offers without any limit",
        )

    def build_options(self, parsed_args: argparse.Namespace) -> PriceSyncCliOptions:
        return PriceSyncCliOptions(
            commit=parsed_args.commit,
            dry_run=parsed_args.dry_run,
            store=parsed_args.store,
            limit=parsed_args.limit,
            no_limit=parsed_args.no_limit,
        )

    async def execute_job(self, session, options: PriceSyncCliOptions) -> PriceSyncCliResult:
        job = PriceSyncCronJob()
        effective_limit = 0 if options.no_limit else options.limit

        logger.info(
            "Staging price sync cycle via transactional outbox [store=%s, limit=%s]...",
            options.store,
            "UNLIMITED" if effective_limit == 0 else effective_limit,
        )
        message_ids = await job.dispatch_once(
            store_key=options.store,
            limit=effective_limit,
            session=session,
            commit=options.commit,
            dry_run=options.dry_run,
        )
        return PriceSyncCliResult(
            store=options.store,
            message_ids=message_ids,
        )

    def render_summary(self, result: PriceSyncCliResult, options: PriceSyncCliOptions) -> None:
        transaction = "COMMITTED" if options.commit else "DRY-RUN (rolled back)"

        print("\n" + "=" * 60, file=self._stdout)
        print("PRICE SYNC CRON CYCLE DISPATCH SUMMARY (OUTBOX)", file=self._stdout)
        print("=" * 60, file=self._stdout)
        print(f"Transaction: {transaction}", file=self._stdout)
        if not result.message_ids:
            print("No stale offers required synchronization.", file=self._stdout)
        else:
            print(
                f"Staged {len(result.message_ids)} outbox batch message(s):",
                file=self._stdout,
            )
            for message_id in result.message_ids:
                print(f"  - Outbox Message ID: {message_id}", file=self._stdout)
            print(
                "\nThe running outbox relay and RabbitMQ consumers will process these batches.",
                file=self._stdout,
            )
        print("=" * 60 + "\n", file=self._stdout)


# Convenience alias for callers that prefer the shorter job-runner name.
PriceSyncCronRunner = PriceSyncCronCliRunner


async def main(argv: list[str] | None = None) -> int:
    """Async entry point used by tests and embedding callers."""
    return await PriceSyncCronCliRunner().run(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
