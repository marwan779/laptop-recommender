"""Unit tests for InboxRepository atomic claims."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.inbox_repository import InboxRepository


@pytest.mark.asyncio
async def test_claim_message_returns_true_for_new_message():
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "event-1"
    session.execute.return_value = result

    repo = InboxRepository(session)
    claimed = await repo.claim_message(
        message_id="event-1",
        event_type="prices.checked.event",
        handler_name="handle_prices_checked_event",
    )

    assert claimed is True
    stmt = session.execute.call_args.args[0]
    sql = str(stmt)
    assert "inbox_message" in sql
    assert "ON CONFLICT" in sql.upper()


@pytest.mark.asyncio
async def test_claim_message_returns_false_for_duplicate():
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    repo = InboxRepository(session)
    claimed = await repo.claim_message(
        message_id="event-1",
        event_type="prices.checked.event",
        handler_name="handle_prices_checked_event",
    )

    assert claimed is False
