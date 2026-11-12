"""Unit tests for OutboxRelayWorker."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest

from app.jobs.outbox_relay import OutboxRelayWorker
from app.models.outbox import OutboxMessage, OutboxStatus


@pytest.mark.asyncio
async def test_outbox_relay_claims_and_publishes_success():
    mock_broker = AsyncMock()
    mock_broker.is_connected = True

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()

    msg1 = OutboxMessage(
        id=uuid.uuid4(),
        event_type="catalog.scrape.command",
        routing_key="catalog.scrape.command",
        payload_json='{"batch_id": "b1", "targets": ["compumarts"]}',
        status=OutboxStatus.PENDING,
        retry_count=0,
        max_retries=3,
        correlation_id="c1",
        created_at=datetime.now(UTC),
    )
    msg2 = OutboxMessage(
        id=uuid.uuid4(),
        event_type="prices.check.command",
        routing_key="prices.check.command",
        payload_json='{"batch_id": "b2", "items": []}',
        status=OutboxStatus.PENDING,
        retry_count=0,
        max_retries=3,
        correlation_id="c2",
        created_at=datetime.now(UTC),
    )

    mock_result.scalars.return_value.all.return_value = [msg1, msg2]
    mock_session.execute.return_value = mock_result

    relay = OutboxRelayWorker(broker=mock_broker)
    processed = await relay.run_once(session=mock_session)

    assert processed == 2
    assert mock_broker.publish.call_count == 2
    # Verify first publish args
    first_call = mock_broker.publish.call_args_list[0]
    assert first_call.kwargs["routing_key"] == "catalog.scrape.command"
    assert first_call.kwargs["message"]["batch_id"] == "b1"

    # Verify session flushed
    mock_session.flush.assert_called()


@pytest.mark.asyncio
async def test_outbox_relay_handles_broker_publish_failure():
    mock_broker = AsyncMock()
    mock_broker.is_connected = True
    mock_broker.publish.side_effect = RuntimeError("RabbitMQ connection reset by peer")

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()

    msg_id = uuid.uuid4()
    msg = OutboxMessage(
        id=msg_id,
        event_type="catalog.scrape.command",
        routing_key="catalog.scrape.command",
        payload_json='{"batch_id": "b-fail"}',
        status=OutboxStatus.PENDING,
        retry_count=0,
        max_retries=3,
        correlation_id="c-fail",
        created_at=datetime.now(UTC),
    )

    mock_result.scalars.return_value.all.return_value = [msg]
    mock_session.execute.return_value = mock_result

    relay = OutboxRelayWorker(broker=mock_broker)
    # mock get_by_id on the internal repository by mocking execute for get_by_id
    mock_get_result = MagicMock()
    mock_get_result.scalar_one_or_none.return_value = msg
    mock_session.execute.side_effect = [mock_result, mock_get_result]

    processed = await relay.run_once(session=mock_session)

    assert processed == 1
    mock_broker.publish.assert_called_once()
    # Should have updated failure in msg
    assert msg.retry_count == 1
    assert "connection reset" in (msg.last_error or "")
    assert msg.status == OutboxStatus.PENDING


@pytest.mark.asyncio
async def test_outbox_relay_connects_if_disconnected():
    mock_broker = AsyncMock()
    mock_broker.is_connected = False

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()

    msg = OutboxMessage(
        id=uuid.uuid4(),
        event_type="test.reconnect",
        routing_key="test.reconnect",
        payload_json='{"ping": "pong"}',
        status=OutboxStatus.PENDING,
        retry_count=0,
        max_retries=3,
        correlation_id="c-reconn",
        created_at=datetime.now(UTC),
    )

    mock_result.scalars.return_value.all.return_value = [msg]
    mock_session.execute.return_value = mock_result

    relay = OutboxRelayWorker(broker=mock_broker)
    processed = await relay.run_once(session=mock_session)

    assert processed == 1
    mock_broker.connect.assert_called_once()
    mock_broker.publish.assert_called_once()


@pytest.mark.asyncio
async def test_outbox_relay_empty_queue():
    mock_broker = AsyncMock()
    mock_broker.is_connected = True

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    relay = OutboxRelayWorker(broker=mock_broker)
    processed = await relay.run_once(session=mock_session)

    assert processed == 0
    mock_broker.publish.assert_not_called()


@pytest.mark.asyncio
async def test_outbox_relay_lifecycle_start_and_stop():
    mock_broker = AsyncMock()
    mock_broker.is_connected = True

    relay = OutboxRelayWorker(broker=mock_broker, poll_interval_seconds=0.1)

    task = relay.start()
    assert task is not None
    assert not task.done()

    # Allow loop to start
    await asyncio.sleep(0.05)

    await relay.stop()
    assert task.done()
    assert relay._task is None


def test_outbox_relay_reads_lease_and_batch_size_from_settings(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "outbox_batch_size", 17)
    monkeypatch.setattr(settings, "outbox_lease_duration_minutes", 9)

    relay = OutboxRelayWorker(broker=AsyncMock())

    assert relay.batch_size == 17
    assert relay.lease_duration_minutes == 9
