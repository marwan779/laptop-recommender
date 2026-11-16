"""CLI polling helpers for watching outbox/consumer progress across flows.

Uses dedicated repositories (`OutboxRepository`, `BatchLogRepository`,
`PriceHistoryRepository`) so CLI scripts contain zero inline SQL.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
import json
from pathlib import Path
import time
from typing import Any, TextIO
import uuid

from app.repositories.batch_log_repository import BatchLogRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.price_history_repository import PriceHistoryRepository

_TERMINAL_CATALOG_STATUSES = frozenset({"SUCCESS", "CHECKPOINT_OK", "PARTIAL", "FAILED"})
_TERMINAL_PRICE_STATUSES = frozenset({"SUCCESS", "PARTIAL", "FAILED"})


async def wait_for_catalog_batch(
    *,
    session_factory: Callable[[], Any],
    batch_id: str,
    stdout: TextIO,
    timeout_seconds: float = 600.0,
    poll_interval: float = 2.0,
) -> int:
    """Poll outbox + ``ScrapingBatchLog`` for Flow 1 until terminal completion or timeout."""
    batch_uuid = uuid.UUID(batch_id)
    deadline = time.monotonic() + timeout_seconds
    last_outbox_status: str | None = None
    last_batch_status: str | None = None

    print(
        f"Waiting for catalog scrape batch [{batch_id}] (timeout={int(timeout_seconds)}s)...", file=stdout, flush=True
    )
    while True:
        async with session_factory() as sess:
            outbox = await OutboxRepository(sess).get_by_id(batch_uuid)
            batch_log = await BatchLogRepository(sess).get_by_id(batch_uuid)

        outbox_status = str(outbox.status) if outbox else "UNKNOWN"
        batch_status = str(batch_log.status) if batch_log else "UNKNOWN"
        if outbox_status != last_outbox_status or batch_status != last_batch_status:
            print(
                f"  [status] outbox={outbox_status}, batch_log={batch_status}",
                file=stdout,
                flush=True,
            )
            last_outbox_status = outbox_status
            last_batch_status = batch_status

        if batch_log and batch_log.status in _TERMINAL_CATALOG_STATUSES:
            _print_catalog_batch_report(batch_log, stdout)
            return 1 if batch_log.status == "FAILED" else 0

        if outbox and str(outbox.status) == "FAILED":
            print(f"[FAILED] Outbox dispatch failed: {outbox.last_error}", file=stdout, flush=True)
            return 1

        if time.monotonic() >= deadline:
            print(
                f"[TIMEOUT] Batch [{batch_id}] did not reach a terminal status within {int(timeout_seconds)}s.",
                file=stdout,
                flush=True,
            )
            return 1

        await asyncio.sleep(poll_interval)


async def wait_for_price_sync_batches(
    *,
    session_factory: Callable[[], Any],
    message_ids: list[str],
    started_at: datetime,
    store_key: str | None,
    stdout: TextIO,
    timeout_seconds: float = 300.0,
    poll_interval: float = 2.0,
) -> int:
    """Poll outbox + ``ScrapingBatchLog`` for Flow 2 and print exact price/stock diffs."""
    batch_uuids = [uuid.UUID(mid) for mid in message_ids]
    deadline = time.monotonic() + timeout_seconds
    last_signature: tuple[int, int] | None = None

    print(
        f"Waiting for {len(batch_uuids)} price check batch(es) (timeout={int(timeout_seconds)}s)...",
        file=stdout,
        flush=True,
    )
    while True:
        async with session_factory() as sess:
            outbox_rows = await OutboxRepository(sess).list_by_ids(batch_uuids)
            log_rows = await BatchLogRepository(sess).list_by_ids(batch_uuids)

        published_count = sum(1 for row in outbox_rows if str(row.status) == "PUBLISHED")
        failed_outbox = [row for row in outbox_rows if str(row.status) == "FAILED"]
        completed_logs = [row for row in log_rows if row.status in _TERMINAL_PRICE_STATUSES]

        sig = (published_count, len(completed_logs))
        if sig != last_signature:
            print(
                f"  [progress] outbox_published={published_count}/{len(batch_uuids)}, "
                f"batches_completed={len(completed_logs)}/{len(batch_uuids)}",
                file=stdout,
                flush=True,
            )
            last_signature = sig

        if len(completed_logs) >= len(batch_uuids):
            async with session_factory() as sess:
                changes = await PriceHistoryRepository(sess).list_changes_since(
                    since=started_at,
                    store_key=store_key,
                    limit=100,
                )
            _print_price_sync_report(completed_logs, changes, stdout)
            return 1 if any(row.status == "FAILED" for row in completed_logs) else 0

        if failed_outbox:
            print(f"[FAILED] Outbox dispatch failed for {len(failed_outbox)} batch(es).", file=stdout, flush=True)
            return 1

        if time.monotonic() >= deadline:
            print(f"[TIMEOUT] Price sync did not complete within {int(timeout_seconds)}s.", file=stdout, flush=True)
            return 1

        await asyncio.sleep(poll_interval)


async def wait_for_reviews_job(
    *,
    session_factory: Callable[[], Any],
    job_id: str,
    stdout: TextIO,
    reviews_dir: Path | None = None,
    timeout_seconds: float = 600.0,
    poll_interval: float = 2.0,
) -> int:
    """Poll outbox, failure audit logs, and optional local artifact file for Flow 3."""
    fail_uuid = uuid.uuid5(uuid.NAMESPACE_OID, f"reviews-failed:{job_id}")
    enrich_fail_uuid = uuid.uuid5(uuid.NAMESPACE_OID, f"reviews-enrich-failed:{job_id}")
    local_artifact = (reviews_dir / f"raw_chassis_reviews_{job_id}.json") if reviews_dir else None
    deadline = time.monotonic() + timeout_seconds
    last_outbox_status: str | None = None

    print(f"Waiting for review job [{job_id}] (timeout={int(timeout_seconds)}s)...", file=stdout, flush=True)
    while True:
        async with session_factory() as sess:
            outbox = await OutboxRepository(sess).get_by_correlation_id(job_id)
            fail_logs = await BatchLogRepository(sess).list_by_ids([fail_uuid, enrich_fail_uuid])

        outbox_status = str(outbox.status) if outbox else "UNKNOWN"
        if outbox_status != last_outbox_status:
            print(f"  [status] outbox={outbox_status}", file=stdout, flush=True)
            last_outbox_status = outbox_status

        if fail_logs:
            for flog in fail_logs:
                print(f"[FAILED] {flog.trigger_type}: {flog.error_message}", file=stdout, flush=True)
            return 1

        if outbox and str(outbox.status) == "FAILED":
            print(f"[FAILED] Outbox dispatch failed: {outbox.last_error}", file=stdout, flush=True)
            return 1

        if local_artifact is not None and local_artifact.is_file():
            _print_local_reviews_report(local_artifact, stdout)
            return 0

        if time.monotonic() >= deadline:
            print(
                f"[TIMEOUT] Review job [{job_id}] did not finish within {int(timeout_seconds)}s.",
                file=stdout,
                flush=True,
            )
            return 1

        await asyncio.sleep(poll_interval)


def _print_catalog_batch_report(batch_log: Any, stdout: TextIO) -> None:
    print("\n" + "=" * 60, file=stdout)
    print("CATALOG SCRAPE EXECUTION RESULT", file=stdout)
    print("=" * 60, file=stdout)
    print(f"Batch ID:         {batch_log.id}", file=stdout)
    print(f"Status:           {batch_log.status}", file=stdout)
    print(f"Items Scraped:    {batch_log.items_scraped}", file=stdout)
    if batch_log.duration_seconds is not None:
        print(f"Duration:         {float(batch_log.duration_seconds):.2f}s", file=stdout)
    if batch_log.pointers_received:
        print(
            f"Pointers Found:   {len(batch_log.pointers_received)} ({', '.join(batch_log.pointers_received[:5])})",
            file=stdout,
        )
    if batch_log.error_message:
        print(f"Error:            {batch_log.error_message}", file=stdout)
    if batch_log.status == "CHECKPOINT_OK":
        print("Disk Output:      services/scraper-service/scraping results/unified_catalog_latest.json", file=stdout)
    print("=" * 60 + "\n", file=stdout, flush=True)


def _print_price_sync_report(logs: list[Any], changes: list[dict[str, Any]], stdout: TextIO) -> None:
    print("\n" + "=" * 72, file=stdout)
    print("PRICE CHECK EXECUTION RESULTS", file=stdout)
    print("=" * 72, file=stdout)
    for row in logs:
        dur = f"{float(row.duration_seconds):.2f}s" if row.duration_seconds is not None else "n/a"
        print(
            f"Store: {row.store_key:<12} Status: {row.status:<8} "
            f"Checked: {row.items_scraped:<4} Updated: {row.offers_updated:<4} Duration: {dur}",
            file=stdout,
        )
    if not changes:
        print("\nNo price or stock changes detected in this run.", file=stdout)
    else:
        print(f"\nDetected {len(changes)} price/stock transition(s):", file=stdout)
        for item in changes[:25]:
            prev = f"{item['previous_price_egp']:,.0f}" if item["previous_price_egp"] is not None else "n/a"
            curr = f"{item['price_egp']:,.0f}"
            stock = "IN_STOCK" if item["in_stock"] else "OUT_OF_STOCK"
            print(
                f"  - [{item['store_key']}] {item['title']} | {prev} -> {curr} EGP | {stock}",
                file=stdout,
            )
    print("=" * 72 + "\n", file=stdout, flush=True)


def _print_local_reviews_report(artifact_path: Path, stdout: TextIO) -> None:
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    meta = data.get("batch_metadata") or {}
    summary = meta.get("metrics_summary") or {}
    print("\n" + "=" * 60, file=stdout)
    print("REVIEWS SCRAPE EXECUTION RESULT", file=stdout)
    print("=" * 60, file=stdout)
    print(f"Job ID:           {meta.get('job_id')}", file=stdout)
    print(f"Chassis Scraped:  {meta.get('total_targets_processed', len(data.get('laptops', [])))}", file=stdout)
    print(f"YouTube Videos:   {summary.get('total_youtube_videos', 0)}", file=stdout)
    print(f"YT Comments:      {summary.get('total_youtube_comments', 0)}", file=stdout)
    print(f"Community Posts:  {summary.get('total_community_posts', 0)}", file=stdout)
    print(f"Saved To:         {artifact_path}", file=stdout)
    print("=" * 60 + "\n", file=stdout, flush=True)
