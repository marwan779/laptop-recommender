"""End-to-end smoke test for the multimedia & community review intelligence pipeline.

What it proves
-------------
1. **Outbound leg** — catalog-service reads laptops from PostgreSQL, resolves
   chassis targets, and publishes ``reviews.scrape.command`` to RabbitMQ.
2. **Worker leg** — scraper-service consumes that command, collects YouTube +
   community evidence, writes a local inspection copy of the artifact, and
   (optionally) uploads it to S3/MinIO.
3. **Return leg** — scraper-service publishes ``reviews.ready.event``; this
   script receives it on a dedicated queue and validates that
   ``payload.job_id`` matches the job it dispatched.

The generated JSON is always persisted to disk for manual inspection. With
``--upload-s3`` it is also uploaded to the configured bucket.

Execution modes
---------------
``single``  Resolve exactly one chassis (by ``--canonical-id``, ``--query``, or
            the first unreviewed laptop). Default timeout: 90s.
``full``    Resolve unreviewed laptops (falling back to all laptops) into
            unique physical chassis targets (189 distinct chassis across 71 families).
            Use ``--limit <N>`` to cap the batch size for fast smoke testing.
            Default timeout: 600s.

Scraper worker handling
-----------------------
Both services expose a top-level package named ``app``, so importing both into
one interpreter is unsafe. This script therefore owns the catalog-service
context (DB + broker) and runs scraper-service in a separate process:

* if a worker is already consuming ``scraper.reviews.jobs`` it is reused;
* otherwise a supervised background worker is started (disable with
  ``--no-auto-worker``), and stopped when the script exits.

Usage
-----
    python scripts/test_reviews_pipeline_e2e.py --query "LOQ 15"
    python scripts/test_reviews_pipeline_e2e.py --canonical-id lenovo-loq-15irx9 --upload-s3
    python scripts/test_reviews_pipeline_e2e.py --mode full --timeout 900

Run it with the catalog-service virtualenv (it needs SQLAlchemy/asyncpg/aio-pika
at minimum):

    services/catalog-service/.venv/Scripts/python.exe scripts/test_reviews_pipeline_e2e.py ...
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import logging
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import uuid

# ── Bootstrap: make catalog-service the active ``app`` package ───────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = REPO_ROOT / "services" / "catalog-service"
SCRAPER_ROOT = REPO_ROOT / "services" / "scraper-service"
DEFAULT_OUTPUT_DIR = SCRAPER_ROOT / "scraping results" / "reviews"

if str(CATALOG_ROOT) not in sys.path:
    sys.path.insert(0, str(CATALOG_ROOT))

import aio_pika  # noqa: E402
from sqlalchemy import or_, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.common.messaging.rabbitmq import RabbitMQBroker  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.domain.reviews import ChassisTargetResolver  # noqa: E402
from app.models.laptop import LaptopConfiguration  # noqa: E402
from app.repositories.laptop_repository import LaptopRepository  # noqa: E402
from app.schemas.events import (  # noqa: E402
    EventType,
    LaptopReviewTarget,
    ReviewsReadyEvent,
    ScrapeReviewsCommand,
    ScrapeReviewsPayload,
)
from app.schemas.reviews_s3 import RawChassisReviewsFile  # noqa: E402
from app.services.catalog_ingestion_service import CatalogIngestionService  # noqa: E402

READY_QUEUE = "test.reviews.ready.e2e"
SCRAPER_QUEUE = "scraper.reviews.jobs"
WORKER_STARTUP_TIMEOUT_SECONDS = 45
ARTIFACT_SETTLE_TIMEOUT_SECONDS = 10

logger = logging.getLogger("e2e.reviews")

# Injected into the scraper subprocess. Values arrive through the environment so
# the source stays static and readable.
WORKER_SOURCE = """
import asyncio
import os
from pathlib import Path

from app.common.messaging.rabbitmq import RabbitMQBroker
from app.services.messaging_consumer import ScraperMessageConsumer
from app.services.reviews.collector import ReviewCollectorService


class _NoOpStorage:
    \"\"\"Placeholder storage backend so dry-runs never initialize S3/MinIO.\"\"\"

    provider_name = "noop"
    bucket_name = "noop"

    def __getattr__(self, name: str):
        raise RuntimeError(f"S3/storage method '{name}' called while upload_to_s3=False.")


async def main() -> None:
    broker = RabbitMQBroker()
    await broker.connect()

    upload_s3 = os.environ.get("E2E_UPLOAD_S3") == "1"
    collector = ReviewCollectorService(
        storage_service=None if upload_s3 else _NoOpStorage(),
        broker=broker,
        upload_to_s3=upload_s3,
        local_output_dir=Path(os.environ["E2E_OUTPUT_DIR"]),
    )
    consumer = ScraperMessageConsumer(broker=broker, review_collector=collector)
    await consumer.start_listening()
    print("[e2e-worker] listening for reviews commands", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await broker.close()


asyncio.run(main())
"""


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="End-to-end smoke test for the reviews intelligence pipeline.",
    )
    parser.add_argument(
        "--mode",
        choices=["single", "full"],
        default="single",
        help="single: one chassis target; full: every unreviewed chassis (default: single).",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Case-insensitive text matched against title, brand, or laptop_model (e.g. 'LOQ 15').",
    )
    parser.add_argument(
        "--canonical-id",
        dest="canonical_id",
        default=None,
        help="Exact canonical slug to select one laptop.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of chassis targets to dispatch (useful for batch testing without scraping all 189 targets).",
    )
    parser.add_argument(
        "--random",
        action="store_true",
        default=False,
        help="Randomly sample up to --limit chassis targets instead of taking the first N.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional RNG seed when --random is used for reproducible sampling.",
    )
    parser.add_argument(
        "--upload-s3",
        action="store_true",
        default=False,
        help="Upload the artifact to the configured S3/MinIO bucket (default: local only).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Local directory for the reviews JSON (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Max seconds to wait for reviews.ready.event (default: 90 single, 600 full).",
    )
    parser.add_argument(
        "--no-auto-worker",
        action="store_true",
        default=False,
        help="Require an already-running scraper worker instead of starting one.",
    )
    return parser.parse_args(argv)


def resolve_output_dir(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path)


def resolve_timeout(args: argparse.Namespace) -> int:
    if args.timeout is not None:
        return max(1, args.timeout)
    return 600 if args.mode == "full" else 90


# ── Database / target resolution ────────────────────────────────────────────


async def select_laptops(args: argparse.Namespace) -> list[LaptopConfiguration]:
    """Return the ORM rows to resolve for the requested mode."""
    async with AsyncSessionLocal() as session:
        repo = LaptopRepository(session)

        if args.mode == "full":
            laptops = list(await repo.get_unreviewed_laptops())
            if not laptops:
                logger.warning("No unreviewed laptops found; falling back to the full catalog.")
                stmt = select(LaptopConfiguration).options(
                    selectinload(LaptopConfiguration.offers),
                )
                laptops = list((await session.execute(stmt)).scalars().unique().all())
            return laptops

        if args.canonical_id:
            laptop = await repo.get_by_canonical_id(args.canonical_id)
            if laptop is None:
                raise SystemExit(f"No laptop found for canonical id '{args.canonical_id}'.")
            return [laptop]

        if args.query:
            pattern = f"%{args.query.strip()}%"
            stmt = (
                select(LaptopConfiguration)
                .options(selectinload(LaptopConfiguration.offers))
                .where(
                    or_(
                        LaptopConfiguration.title.ilike(pattern),
                        LaptopConfiguration.brand.ilike(pattern),
                        LaptopConfiguration.laptop_model.ilike(pattern),
                    )
                )
                .order_by(LaptopConfiguration.laptop_added_at.asc())
                .limit(1)
            )
            laptop = (await session.execute(stmt)).scalars().first()
            if laptop is None:
                raise SystemExit(f"No laptop matched query '{args.query}'.")
            return [laptop]

        unreviewed = list(await repo.get_unreviewed_laptops())
        if unreviewed:
            return unreviewed[:1]

        fallback = (
            await session.execute(
                select(LaptopConfiguration)
                .options(selectinload(LaptopConfiguration.offers))
                .order_by(LaptopConfiguration.laptop_added_at.asc())
                .limit(1)
            )
        ).scalars().first()
        if fallback is None:
            raise SystemExit("The catalog database contains no laptops.")
        return [fallback]


def build_targets(laptops: list[LaptopConfiguration]) -> list[LaptopReviewTarget]:
    """Project ORM rows into resolved chassis targets (includes screen_size)."""
    inputs = [CatalogIngestionService._to_review_input(laptop) for laptop in laptops]
    resolved = ChassisTargetResolver().resolve(inputs)
    return [CatalogIngestionService._to_review_target(target) for target in resolved]


# ── RabbitMQ plumbing ───────────────────────────────────────────────────────


async def count_queue_consumers(queue_name: str) -> int:
    """Return the consumer count for a queue, or 0 when it does not exist."""
    connection = None
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        queue = await channel.declare_queue(queue_name, passive=True)
        declaration = queue.declaration_result
        return int(getattr(declaration, "consumer_count", 0) or 0)
    except Exception:  # noqa: BLE001 - absence of the queue simply means "no worker"
        return 0
    finally:
        if connection is not None and not connection.is_closed:
            await connection.close()


async def purge_queue(queue_name: str) -> int:
    """Purge stale unconsumed messages from a queue before test dispatch."""
    connection = None
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        queue = await channel.declare_queue(queue_name, passive=True)
        purged = await queue.purge()
        return int(purged.message_count or 0)
    except Exception:  # noqa: BLE001
        return 0
    finally:
        if connection is not None and not connection.is_closed:
            await connection.close()


def scraper_python() -> str:
    """Prefer the scraper-service virtualenv interpreter when present."""
    candidates = [
        SCRAPER_ROOT / ".venv" / "Scripts" / "python.exe",
        SCRAPER_ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


async def start_worker(output_dir: Path, upload_s3: bool) -> subprocess.Popen:
    """Start a supervised scraper worker subprocess and wait until it consumes."""
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "e2e_worker.log"
    log_handle = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 - owned by the subprocess lifetime

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SCRAPER_ROOT), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    env["E2E_UPLOAD_S3"] = "1" if upload_s3 else "0"
    env["E2E_OUTPUT_DIR"] = str(output_dir)

    logger.info("Starting scraper worker (%s)...", scraper_python())
    process = subprocess.Popen(
        [scraper_python(), "-u", "-c", WORKER_SOURCE],
        cwd=str(SCRAPER_ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    process._e2e_log_handle = log_handle  # type: ignore[attr-defined]
    process._e2e_log_path = log_path  # type: ignore[attr-defined]

    deadline = time.monotonic() + WORKER_STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Scraper worker exited during startup (code {process.returncode}). "
                f"See {log_path}."
            )
        if await count_queue_consumers(SCRAPER_QUEUE) > 0:
            logger.info("Scraper worker is consuming '%s'.", SCRAPER_QUEUE)
            return process
        await asyncio.sleep(1.0)

    stop_worker(process)
    raise RuntimeError(f"Scraper worker did not start consuming within {WORKER_STARTUP_TIMEOUT_SECONDS}s.")


def stop_worker(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    handle = getattr(process, "_e2e_log_handle", None)
    if handle is not None:
        handle.close()


# ── Artifact verification ───────────────────────────────────────────────────


def locate_artifact(output_dir: Path, job_id: str) -> Path:
    return output_dir / f"raw_chassis_reviews_{job_id}.json"


async def wait_for_artifact(path: Path, timeout: float = ARTIFACT_SETTLE_TIMEOUT_SECONDS) -> Path:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return path
        await asyncio.sleep(0.25)
    raise RuntimeError(f"Artifact not found at '{path}' after {timeout}s.")


def verify_artifact(path: Path, job_id: str, expected_targets: int) -> RawChassisReviewsFile:
    artifact = RawChassisReviewsFile.model_validate_json(path.read_text(encoding="utf-8"))
    if artifact.batch_metadata.job_id != job_id:
        raise RuntimeError(
            f"Artifact job_id mismatch: expected '{job_id}', got '{artifact.batch_metadata.job_id}'."
        )
    if len(artifact.laptops) != expected_targets:
        raise RuntimeError(
            f"Artifact chassis count mismatch: expected {expected_targets}, got {len(artifact.laptops)}."
        )
    return artifact


# ── Main flow ───────────────────────────────────────────────────────────────


async def dispatch_and_wait(
    command: ScrapeReviewsCommand,
    job_id: str,
    timeout: int,
) -> ReviewsReadyEvent:
    """Publish the command and wait for the matching reviews.ready.event."""
    broker = RabbitMQBroker()
    loop = asyncio.get_running_loop()
    ready_future: asyncio.Future[ReviewsReadyEvent] = loop.create_future()

    async def on_reviews_ready(raw: dict) -> None:
        try:
            event = ReviewsReadyEvent.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - ignore unrelated messages
            logger.debug("Ignoring malformed reviews.ready.event: %s", exc)
            return
        if event.payload.job_id != job_id:
            logger.debug(
                "Ignoring reviews.ready.event for a different job ('%s').", event.payload.job_id
            )
            return
        if not ready_future.done():
            ready_future.set_result(event)

    await broker.connect()
    try:
        await broker.subscribe(
            queue_name=READY_QUEUE,
            routing_key=EventType.REVIEWS_READY_EVENT,
            handler=on_reviews_ready,
            prefetch_count=1,
        )

        dispatched_at = datetime.now(UTC)
        started = time.perf_counter()
        logger.info(
            "[%s] Publishing %s with %d chassis targets to exchange '%s'.",
            dispatched_at.isoformat(),
            EventType.REVIEWS_SCRAPE_COMMAND,
            len(command.payload.targets),
            settings.rabbitmq_exchange_name,
        )
        await broker.publish(
            routing_key=EventType.REVIEWS_SCRAPE_COMMAND,
            message=command,
        )

        event = await asyncio.wait_for(ready_future, timeout=timeout)
        elapsed = time.perf_counter() - started
        logger.info("Received reviews.ready.event after %.2fs.", elapsed)
        return event
    finally:
        await broker.close()


def print_targets(targets: list[LaptopReviewTarget]) -> None:
    print(f"\nSelected {len(targets)} chassis target(s) to dispatch:")
    for index, target in enumerate(targets[:15], start=1):
        size = f"{target.screen_size}in" if target.screen_size is not None else "size?"
        grouped = len(target.matched_laptop_ids)
        print(
            f"  {index:>2}. [{target.chassis_key or '?'}] "
            f"{target.brand or '?'} {target.laptop_family or '?'} "
            f"{target.laptop_model or '?'} [{size}] "
            f"(grouped={grouped}, canonical={target.canonical_id})"
        )
    if len(targets) > 15:
        print(f"  ... and {len(targets) - 15} more")


def _count_duplicates(values: list[str]) -> int:
    cleaned = [val for val in values if val]
    return len(cleaned) - len(set(cleaned))


def print_summary(
    artifact: RawChassisReviewsFile,
    path: Path,
    event: ReviewsReadyEvent,
) -> None:
    summary = artifact.batch_metadata.metrics_summary
    total_editorial = sum(len(item.communities.editorial) for item in artifact.laptops)
    total_discussions = sum(len(item.communities.discussions) for item in artifact.laptops)

    print("\n" + "=" * 78)
    print("REVIEWS PIPELINE E2E SUMMARY")
    print("=" * 78)
    print(f"job_id                : {artifact.batch_metadata.job_id}")
    print(f"local artifact        : {path}")
    print(f"event s3_key          : {event.payload.s3_key}")
    print(f"chassis in artifact   : {len(artifact.laptops)}")
    print(f"laptops aggregated    : {sum(len(i.matched_laptop_ids) for i in artifact.laptops)}")
    print(f"youtube videos        : {summary.total_youtube_videos}")
    print(f"youtube comments      : {summary.total_youtube_comments}")
    print(f"editorial reviews     : {total_editorial}")
    print(f"forum discussions     : {total_discussions}")
    print(f"event total_chassis   : {event.payload.total_chassis}")
    print(f"event total_laptops   : {event.payload.total_laptops}")
    print("=" * 78)

    for index, item in enumerate(artifact.laptops, start=1):
        yt = item.youtube
        video_ids = [v.video_id for v in yt.videos]
        video_urls = [v.video_url for v in yt.videos]
        transcripts_ok = sum(1 for v in yt.videos if v.transcript_text.strip())
        yt_comments = sum(len(v.top_comments) for v in yt.videos)
        editorial_urls = [e.review_url for e in item.communities.editorial]
        discussion_urls = [d.post_url for d in item.communities.discussions]

        print(
            f"\n[{index}] chassis_key={item.chassis_key} | "
            f"canonical={item.primary_canonical_id} | matched_laptops={len(item.matched_laptop_ids)}"
        )
        print(
            f"    YouTube : query={yt.query_used!r} | found={yt.total_videos_found} | "
            f"kept={len(yt.videos)} | dup_ids={_count_duplicates(video_ids)} | "
            f"dup_urls={_count_duplicates(video_urls)} | transcripts={transcripts_ok}/{len(yt.videos)} | "
            f"comments={yt_comments}"
        )
        for v_idx, video in enumerate(yt.videos, start=1):
            t_len = len(video.transcript_text.strip())
            print(
                f"      {v_idx}. [{video.language}, chars={t_len}, comments={len(video.top_comments)}] "
                f"{video.title} -> {video.video_url}"
            )

        print(
            f"    Editorial ({len(item.communities.editorial)}, dup_urls={_count_duplicates(editorial_urls)})"
        )
        for rev in item.communities.editorial:
            print(
                f"      - [{rev.source}, verdict_chars={len(rev.verdict)}] {rev.review_url}"
            )

        print(
            f"    Discussions ({len(item.communities.discussions)}, dup_urls={_count_duplicates(discussion_urls)})"
        )
        for post in item.communities.discussions:
            print(
                f"      - [{post.platform}, comments={len(post.comments)}] "
                f"{post.post_title} -> {post.post_url}"
            )


async def run(args: argparse.Namespace) -> int:
    timeout = resolve_timeout(args)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Reviews pipeline E2E")
    print(f"  mode          : {args.mode}")
    print(f"  database      : {settings.async_database_url.split('@')[-1]}")
    print(f"  rabbitmq      : {settings.rabbitmq_url.split('@')[-1]}")
    print(f"  exchange      : {settings.rabbitmq_exchange_name}")
    print(f"  output dir    : {output_dir}")
    print(f"  upload to s3  : {args.upload_s3}")
    if args.limit is not None:
        print(f"  limit         : {args.limit} (random={args.random})")
    print(f"  timeout       : {timeout}s")

    try:
        laptops = await select_laptops(args)
        targets = build_targets(laptops)
        print(
            f"\nCatalog resolution: {len(laptops)} SQL laptop(s) -> "
            f"{len(targets)} unique chassis target(s)."
        )
        if args.limit is not None and args.limit > 0:
            if args.random:
                rng = random.Random(args.seed) if args.seed is not None else random.Random()
                targets = rng.sample(targets, min(args.limit, len(targets)))
            else:
                targets = targets[: args.limit]
    finally:
        await engine.dispose()

    if not targets:
        print("No chassis targets resolved; nothing to dispatch.", file=sys.stderr)
        return 1

    print_targets(targets)

    job_id = f"e2e-test-{uuid.uuid4().hex[:8]}"
    command = ScrapeReviewsCommand(payload=ScrapeReviewsPayload(job_id=job_id, targets=targets))

    worker: subprocess.Popen | None = None
    consumers = await count_queue_consumers(SCRAPER_QUEUE)
    if consumers == 0:
        purged = await purge_queue(SCRAPER_QUEUE)
        if purged > 0:
            logger.info("Purged %d stale message(s) from '%s'.", purged, SCRAPER_QUEUE)
    if consumers > 0:
        logger.info("Reusing %d existing consumer(s) on '%s'.", consumers, SCRAPER_QUEUE)
        if args.upload_s3:
            logger.warning(
                "--upload-s3 only controls an auto-started worker; the external worker "
                "uses its own upload configuration."
            )
        if output_dir != DEFAULT_OUTPUT_DIR:
            logger.warning(
                "An external worker writes to its own configured output directory; "
                "artifact verification expects '%s'.",
                output_dir,
            )
    elif args.no_auto_worker:
        print(
            f"No worker is consuming '{SCRAPER_QUEUE}' and --no-auto-worker was set.",
            file=sys.stderr,
        )
        return 1
    else:
        worker = await start_worker(output_dir, bool(args.upload_s3))

    started = time.monotonic()
    try:
        event = await dispatch_and_wait(command, job_id, timeout)
        artifact_path = locate_artifact(output_dir, job_id)
        if not artifact_path.exists():
            artifact_path = await wait_for_artifact(artifact_path)
        artifact = verify_artifact(artifact_path, job_id, len(targets))
    except TimeoutError:
        print(
            f"\nFAILED: no matching reviews.ready.event within {timeout}s. "
            f"Check the worker log: {output_dir / 'e2e_worker.log'}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI must report, not traceback
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        stop_worker(worker)

    elapsed = time.monotonic() - started
    print_summary(artifact, artifact_path, event)
    print(f"\nRound trip completed in {elapsed:.2f}s")
    print("BIDIRECTIONAL EVENT LOOP VERIFIED: command dispatched, artifact persisted, ready event received.")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
