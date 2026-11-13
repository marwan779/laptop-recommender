"""Tests for the standalone CLI job runner framework and both job adapters."""

from __future__ import annotations

from dataclasses import dataclass
import io
from unittest.mock import AsyncMock
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.base_cli import BaseCliJobOptions, BaseCliJobRunner
from app.models.laptop import LaptopConfiguration
from app.models.offer import LaptopOffer
from app.models.outbox import OutboxMessage
from app.models.scraping import ScrapingBatchLog, StoreScrapingPointer
from app.schemas.events import EventType
from scripts.run_price_sync_cron import PriceSyncCronCliRunner
from scripts.run_scraping_cron import ScrapingCronCliRunner


def _fake_engine() -> AsyncMock:
    """Engine double whose async dispose() can be asserted without touching PostgreSQL."""
    return AsyncMock()


def _unique_store_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _count_outbox(session: AsyncSession, event_type: str | None = None) -> int:
    stmt = select(func.count()).select_from(OutboxMessage)
    if event_type is not None:
        stmt = stmt.where(OutboxMessage.event_type == event_type)
    return int((await session.execute(stmt)).scalar_one())


async def _seed_scraping_pointer(session: AsyncSession, store_key: str) -> None:
    pointer = StoreScrapingPointer(
        store_key=store_key,
        store_name="CLI Test Store",
        store_domain="cli-test.example",
        latest_pointers=["CLI Watermark Model"],
        total_active_offers=10,
        is_active=True,
    )
    await session.merge(pointer)
    await session.commit()


async def _seed_stale_offer(session: AsyncSession, store_key: str) -> uuid.UUID:
    laptop_id = uuid.uuid4()
    laptop = LaptopConfiguration(
        id=laptop_id,
        canonical_id=f"cli-test-laptop-{uuid.uuid4().hex[:8]}",
        brand="Lenovo",
        laptop_model="Legion 5",
        title="Lenovo Legion 5",
        cpu_manufacturer="AMD",
        cpu_model="Ryzen 7",
        cpu_cores=8,
        cpu_threads=16,
        gpu_manufacturer="NVIDIA",
        gpu_model="RTX 4060",
        ram_capacity_gb=16,
        ram_type="DDR5",
        storage_capacity_gb=1024,
        display_size_inches=15.6,
        display_resolution="1920x1080",
        display_width=1920,
        display_height=1080,
        min_price_egp=55000.0,
        cheapest_store=store_key,
    )
    await session.merge(laptop)

    offer = LaptopOffer(
        id=uuid.uuid4(),
        laptop_configuration_id=laptop_id,
        store_key=store_key,
        store_name="CLI Test Store",
        product_url=f"https://{store_key}.example/legion5",
        price_egp=55000.0,
        in_stock=True,
        is_valid_price=True,
    )
    await session.merge(offer)
    await session.commit()
    return offer.id


class ObservingScrapingCliRunner(ScrapingCronCliRunner):
    """Records the staged rows inside the transaction before the base runner rolls back."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.observed_batch_rows = 0
        self.observed_outbox_rows = 0
        self.store_key = ""

    async def execute_job(self, session, options):
        result = await super().execute_job(session, options)
        self.store_key = options.store
        await session.flush()
        self.observed_batch_rows = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ScrapingBatchLog)
                    .where(ScrapingBatchLog.store_key == options.store)
                )
            ).scalar_one()
        )
        self.observed_outbox_rows = await _count_outbox(
            session, EventType.CATALOG_SCRAPE_COMMAND
        )
        return result


@pytest.mark.asyncio
async def test_scraping_runner_requires_commit_or_dry_run():
    runner = ScrapingCronCliRunner(session_factory=lambda: AsyncMock(), engine=_fake_engine())

    with pytest.raises(SystemExit) as exc_info:
        await runner.run(["--store", "compumarts"])

    assert exc_info.value.code == 2


@pytest.mark.asyncio
async def test_price_sync_runner_requires_commit_or_dry_run():
    runner = PriceSyncCronCliRunner(session_factory=lambda: AsyncMock(), engine=_fake_engine())

    with pytest.raises(SystemExit) as exc_info:
        await runner.run(["--store", "compumarts"])

    assert exc_info.value.code == 2


@pytest.mark.asyncio
async def test_scraping_cli_dry_run_stages_then_rolls_back(db_session: AsyncSession):
    store_key = _unique_store_key("cli-dry-run")
    await _seed_scraping_pointer(db_session, store_key)

    outbox_before = await _count_outbox(db_session)
    engine = _fake_engine()
    runner = ObservingScrapingCliRunner(
        session_factory=lambda: db_session,
        engine=engine,
        stdout=io.StringIO(),
    )

    exit_code = await runner.run(["--dry-run", "--store", store_key])

    assert exit_code == 0
    # The rows existed during execution and were validated via flush...
    assert runner.observed_batch_rows == 1
    assert runner.observed_outbox_rows >= 1
    # ...but the base runner rolled the transaction back afterwards.
    batch_rows = int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(ScrapingBatchLog)
                .where(ScrapingBatchLog.store_key == store_key)
            )
        ).scalar_one()
    )
    assert batch_rows == 0
    assert await _count_outbox(db_session) == outbox_before
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_scraping_cli_commit_persists_batch_and_outbox(db_session: AsyncSession):
    store_key = _unique_store_key("cli-commit")
    await _seed_scraping_pointer(db_session, store_key)

    engine = _fake_engine()
    runner = ScrapingCronCliRunner(
        session_factory=lambda: db_session,
        engine=engine,
        stdout=io.StringIO(),
    )

    exit_code = await runner.run(["--commit", "--store", store_key])

    assert exit_code == 0

    batch_log = (
        await db_session.execute(
            select(ScrapingBatchLog).where(ScrapingBatchLog.store_key == store_key)
        )
    ).scalar_one()
    assert batch_log.status == "QUEUED"

    outbox_event = (
        await db_session.execute(
            select(OutboxMessage).where(
                OutboxMessage.event_type == EventType.CATALOG_SCRAPE_COMMAND,
                OutboxMessage.payload_json.like(f"%{store_key}%"),
            )
        )
    ).scalar_one()
    assert outbox_event.routing_key == EventType.CATALOG_SCRAPE_COMMAND
    assert outbox_event.status == "PENDING"
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_price_sync_cli_outbox_dry_run_rolls_back(db_session: AsyncSession):
    store_key = _unique_store_key("cli-price-dry")
    await _seed_stale_offer(db_session, store_key)

    outbox_before = await _count_outbox(db_session, EventType.PRICES_CHECK_COMMAND)
    engine = _fake_engine()
    runner = PriceSyncCronCliRunner(
        session_factory=lambda: db_session,
        engine=engine,
        stdout=io.StringIO(),
    )

    exit_code = await runner.run(
        ["--dry-run", "--store", store_key, "--limit", "5", "--mode", "outbox"]
    )

    assert exit_code == 0
    assert await _count_outbox(db_session, EventType.PRICES_CHECK_COMMAND) == outbox_before
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_price_sync_cli_outbox_commit_persists_check_prices_commands(
    db_session: AsyncSession,
):
    store_key = _unique_store_key("cli-price-commit")
    await _seed_stale_offer(db_session, store_key)

    engine = _fake_engine()
    runner = PriceSyncCronCliRunner(
        session_factory=lambda: db_session,
        engine=engine,
        stdout=io.StringIO(),
    )

    exit_code = await runner.run(
        ["--commit", "--store", store_key, "--limit", "5", "--mode", "outbox"]
    )

    assert exit_code == 0

    outbox_rows = (
        await db_session.execute(
            select(OutboxMessage).where(
                OutboxMessage.event_type == EventType.PRICES_CHECK_COMMAND,
                OutboxMessage.payload_json.like(f"%{store_key}%"),
            )
        )
    ).scalars().all()
    assert len(outbox_rows) >= 1
    assert all(row.routing_key == EventType.PRICES_CHECK_COMMAND for row in outbox_rows)
    engine.dispose.assert_awaited_once()


class ExplodingCliRunner(BaseCliJobRunner[BaseCliJobOptions, None]):
    """Runner whose domain hook always fails to exercise exit-code guarantees."""

    description = "Exploding test runner"

    def build_options(self, parsed_args) -> BaseCliJobOptions:
        return BaseCliJobOptions(commit=parsed_args.commit, dry_run=parsed_args.dry_run)

    async def execute_job(self, session, options) -> None:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_unhandled_job_error_returns_exit_1_and_disposes_engine(db_session: AsyncSession):
    engine = _fake_engine()
    runner = ExplodingCliRunner(
        session_factory=lambda: db_session,
        engine=engine,
        stdout=io.StringIO(),
    )

    exit_code = await runner.run(["--dry-run"])

    assert exit_code == 1
    engine.dispose.assert_awaited_once()


@dataclass
class CustomCliOptions(BaseCliJobOptions):
    custom_flag: bool = False
    custom_value: str = ""


class CustomCliRunner(BaseCliJobRunner[CustomCliOptions, CustomCliOptions]):
    """Extension proving new flags/options need no BaseCliJobRunner changes."""

    description = "Custom extension runner"

    def register_arguments(self, parser) -> None:
        parser.add_argument("--custom-flag", action="store_true")
        parser.add_argument("--custom-value", type=str, default="default")

    def build_options(self, parsed_args) -> CustomCliOptions:
        return CustomCliOptions(
            commit=parsed_args.commit,
            dry_run=parsed_args.dry_run,
            custom_flag=parsed_args.custom_flag,
            custom_value=parsed_args.custom_value,
        )

    async def execute_job(self, session, options) -> CustomCliOptions:
        self.received_options = options
        return options


@pytest.mark.asyncio
async def test_base_runner_is_open_for_extension_with_custom_flags(db_session: AsyncSession):
    engine = _fake_engine()
    runner = CustomCliRunner(
        session_factory=lambda: db_session,
        engine=engine,
        stdout=io.StringIO(),
    )

    exit_code = await runner.run(
        ["--dry-run", "--custom-flag", "--custom-value", "extended"]
    )

    assert exit_code == 0
    assert runner.received_options.custom_flag is True
    assert runner.received_options.custom_value == "extended"
    assert runner.received_options.dry_run is True
    engine.dispose.assert_awaited_once()
