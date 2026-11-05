"""Unit tests for OutboxRepository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest

from app.models.outbox import OutboxMessage, OutboxStatus
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.events import ScrapeCatalogCommand, ScrapeCatalogPayload


@pytest.mark.asyncio
async def test_insert_outbox_event_with_pydantic():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = OutboxRepository(mock_session)

    cmd = ScrapeCatalogCommand(
        payload=ScrapeCatalogPayload(
            batch_id="batch-123",
            targets=["compumarts"],
            level=2,
        )
    )

    msg = await repo.insert_outbox_event(
        event_type="catalog.scrape.command",
        routing_key="catalog.scrape.command",
        payload=cmd,
        correlation_id="corr-999",
    )

    mock_session.add.assert_called_once_with(msg)
    mock_session.flush.assert_called_once()

    assert msg.event_type == "catalog.scrape.command"
    assert msg.routing_key == "catalog.scrape.command"
    assert msg.status == OutboxStatus.PENDING
    assert msg.retry_count == 0
    assert msg.max_retries == 5
    assert msg.correlation_id == "corr-999"
    assert "batch-123" in msg.payload_json


@pytest.mark.asyncio
async def test_insert_outbox_event_with_dict():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = OutboxRepository(mock_session)

    raw_data = {"key": "value", "count": 42}
    msg = await repo.insert_outbox_event(
        event_type="test.event",
        routing_key="test.key",
        payload=raw_data,
    )

    mock_session.add.assert_called_once_with(msg)
    assert msg.event_type == "test.event"
    assert '"key": "value"' in msg.payload_json
    assert msg.status == OutboxStatus.PENDING


@pytest.mark.asyncio
async def test_claim_batch():
    mock_session = AsyncMock()
    mock_result = MagicMock()

    msg1 = OutboxMessage(
        id=uuid.uuid4(),
        event_type="test.1",
        routing_key="test.1",
        payload_json="{}",
        status=OutboxStatus.PENDING,
        retry_count=0,
        max_retries=3,
        correlation_id="c1",
        created_at=datetime.now(UTC),
    )
    msg2 = OutboxMessage(
        id=uuid.uuid4(),
        event_type="test.2",
        routing_key="test.2",
        payload_json="{}",
        status=OutboxStatus.PENDING,
        retry_count=0,
        max_retries=3,
        correlation_id="c2",
        created_at=datetime.now(UTC),
    )

    mock_result.scalars.return_value.all.return_value = [msg1, msg2]
    mock_session.execute.return_value = mock_result

    repo = OutboxRepository(mock_session)
    claimed = await repo.claim_batch(batch_size=10)

    assert len(claimed) == 2
    assert claimed[0].status == OutboxStatus.PUBLISHING
    assert claimed[1].status == OutboxStatus.PUBLISHING
    mock_session.execute.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_mark_as_dispatched():
    mock_session = AsyncMock()
    repo = OutboxRepository(mock_session)

    id1 = uuid.uuid4()
    id2 = uuid.uuid4()

    await repo.mark_as_dispatched([id1, id2])

    mock_session.execute.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_mark_failed_retry():
    mock_session = AsyncMock()
    msg_id = uuid.uuid4()

    msg = OutboxMessage(
        id=msg_id,
        event_type="test.retry",
        routing_key="test.retry",
        payload_json="{}",
        status=OutboxStatus.PUBLISHING,
        retry_count=1,
        max_retries=3,
        correlation_id="c-retry",
        created_at=datetime.now(UTC),
    )

    repo = OutboxRepository(mock_session)
    repo.get_by_id = AsyncMock(return_value=msg)

    updated = await repo.mark_failed(msg_id, error_message="Temporary socket timeout")

    assert updated is not None
    assert updated.retry_count == 2
    assert updated.status == OutboxStatus.PENDING
    assert updated.last_error == "Temporary socket timeout"
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_mark_failed_terminal():
    mock_session = AsyncMock()
    msg_id = uuid.uuid4()

    msg = OutboxMessage(
        id=msg_id,
        event_type="test.terminal",
        routing_key="test.terminal",
        payload_json="{}",
        status=OutboxStatus.PUBLISHING,
        retry_count=2,
        max_retries=3,
        correlation_id="c-terminal",
        created_at=datetime.now(UTC),
    )

    repo = OutboxRepository(mock_session)
    repo.get_by_id = AsyncMock(return_value=msg)

    updated = await repo.mark_failed(msg_id, error_message="Fatal broker rejection: payload malformed")

    assert updated is not None
    assert updated.retry_count == 3
    assert updated.status == OutboxStatus.FAILED
    assert updated.last_error == "Fatal broker rejection: payload malformed"
    mock_session.flush.assert_called_once()
