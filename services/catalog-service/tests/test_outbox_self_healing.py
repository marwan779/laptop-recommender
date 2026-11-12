"""Unit tests for outbox lease self-healing and event id alignment."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from app.models.outbox import OutboxMessage, OutboxStatus
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.events import ScrapeCatalogCommand, ScrapeCatalogPayload


def _message(status: OutboxStatus, leased_at: datetime | None, retry_count: int = 0) -> OutboxMessage:
    return OutboxMessage(
        id=uuid.uuid4(),
        event_id=str(uuid.uuid4()),
        event_type="catalog.scrape.command",
        routing_key="catalog.scrape.command",
        payload_json="{}",
        status=status,
        retry_count=retry_count,
        max_retries=5,
        correlation_id="corr",
        created_at=datetime.now(UTC) - timedelta(minutes=30),
        leased_at=leased_at,
    )


@pytest.mark.asyncio
async def test_claim_batch_reclaims_expired_publishing_lease():
    mock_session = AsyncMock()
    mock_result = MagicMock()

    stale = _message(
        OutboxStatus.PUBLISHING,
        leased_at=datetime.now(UTC) - timedelta(minutes=10),
        retry_count=1,
    )
    pending = _message(OutboxStatus.PENDING, leased_at=None)

    mock_result.scalars.return_value.all.return_value = [pending, stale]
    mock_session.execute.return_value = mock_result

    repo = OutboxRepository(mock_session)
    claimed = await repo.claim_batch(batch_size=10, lease_duration_minutes=5)

    assert len(claimed) == 2

    # Both messages are now leased.
    assert pending.status == OutboxStatus.PUBLISHING
    assert pending.leased_at is not None
    assert stale.status == OutboxStatus.PUBLISHING
    assert stale.leased_at is not None

    # The stale zombie message consumed one retry attempt.
    assert stale.retry_count == 2
    assert stale.last_error is not None
    assert "Reclaimed zombie message" in stale.last_error

    # Pending messages are not penalized.
    assert pending.retry_count == 0

    # The generated query targets both PENDING rows and expired PUBLISHING rows.
    executed_stmt = mock_session.execute.call_args.args[0]
    sql = str(executed_stmt)
    assert "outbox_message.status" in sql
    assert "outbox_message.leased_at <" in sql


@pytest.mark.asyncio
async def test_claim_batch_does_not_penalize_fresh_publishing_lease():
    mock_session = AsyncMock()
    mock_result = MagicMock()

    fresh = _message(
        OutboxStatus.PUBLISHING,
        leased_at=datetime.now(UTC) - timedelta(seconds=30),
        retry_count=2,
    )
    mock_result.scalars.return_value.all.return_value = [fresh]
    mock_session.execute.return_value = mock_result

    repo = OutboxRepository(mock_session)
    claimed = await repo.claim_batch(batch_size=10, lease_duration_minutes=5)

    assert claimed == [fresh]
    assert fresh.retry_count == 2
    assert fresh.last_error is None


@pytest.mark.asyncio
async def test_insert_outbox_event_reuses_domain_event_id():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = OutboxRepository(mock_session)

    command = ScrapeCatalogCommand(
        payload=ScrapeCatalogPayload(batch_id=str(uuid.uuid4()), targets=["compumarts"])
    )

    msg = await repo.insert_outbox_event(
        event_type="catalog.scrape.command",
        routing_key="catalog.scrape.command",
        payload=command,
    )

    assert msg.event_id == command.event_id
    # The published payload and the outbox row share the same id.
    assert command.event_id in msg.payload_json


@pytest.mark.asyncio
async def test_insert_outbox_event_falls_back_to_outbox_id_for_plain_strings():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = OutboxRepository(mock_session)

    msg = await repo.insert_outbox_event(
        event_type="legacy.event",
        routing_key="legacy.event",
        payload="not-json",
    )

    assert msg.event_id == str(msg.id)
