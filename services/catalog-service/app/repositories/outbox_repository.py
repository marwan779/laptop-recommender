"""Outbox Repository for Transactional Outbox Pattern.

Encapsulates SQL persistence, atomic leasing with row locking, and lifecycle
state transitions for outbox messages.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
import json
from typing import Any
import uuid

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxMessage, OutboxStatus
from app.repositories.base import BaseRepository


class OutboxRepository(BaseRepository[OutboxMessage]):
    """Repository handling SQL persistence and concurrent batch leasing for Transactional Outbox."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(OutboxMessage, session)

    async def insert_outbox_event(
        self,
        event_type: str,
        routing_key: str,
        payload: BaseModel | dict[str, Any] | str,
        correlation_id: str | None = None,
        max_retries: int = 5,
        message_id: uuid.UUID | None = None,
    ) -> OutboxMessage:
        """Insert a pending outbox message within the active database transaction."""
        if isinstance(payload, BaseModel):
            payload_json = payload.model_dump_json()
        elif isinstance(payload, dict):
            payload_json = json.dumps(payload, default=str)
        elif isinstance(payload, str):
            payload_json = payload
        else:
            raise TypeError(f"Unsupported payload type: {type(payload)}. Must be BaseModel, dict, or str.")

        msg = OutboxMessage(
            id=message_id or uuid.uuid4(),
            event_type=event_type,
            routing_key=routing_key,
            payload_json=payload_json,
            status=OutboxStatus.PENDING,
            retry_count=0,
            max_retries=max_retries,
            last_error=None,
            correlation_id=correlation_id or str(uuid.uuid4()),
            created_at=datetime.now(UTC),
            published_at=None,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def claim_batch(
        self,
        batch_size: int = 50,
    ) -> Sequence[OutboxMessage]:
        """Claim a batch of pending messages using SKIP LOCKED to prevent concurrency races.

        Transitions claimed messages to PUBLISHING status before returning them.
        """
        stmt = (
            select(OutboxMessage)
            .where(
                OutboxMessage.status == OutboxStatus.PENDING,
                OutboxMessage.retry_count < OutboxMessage.max_retries,
            )
            .order_by(OutboxMessage.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        messages = result.scalars().all()

        for msg in messages:
            msg.status = OutboxStatus.PUBLISHING

        if messages:
            await self.session.flush()

        return messages

    async def mark_as_dispatched(
        self,
        message_ids: Sequence[uuid.UUID] | uuid.UUID,
        published_at: datetime | None = None,
    ) -> None:
        """Mark one or more messages as successfully published."""
        ids = [message_ids] if isinstance(message_ids, uuid.UUID) else list(message_ids)
        if not ids:
            return

        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id.in_(ids))
            .values(
                status=OutboxStatus.PUBLISHED,
                published_at=published_at or datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def mark_failed(
        self,
        message_id: uuid.UUID,
        error_message: str,
    ) -> OutboxMessage | None:
        """Handle publish failure: increment retry count, record error, and update status."""
        msg = await self.get_by_id(message_id)
        if not msg:
            return None

        msg.retry_count += 1
        msg.last_error = error_message[:1000] if error_message else None

        if msg.retry_count >= msg.max_retries:
            msg.status = OutboxStatus.FAILED
        else:
            msg.status = OutboxStatus.PENDING

        await self.session.flush()
        return msg
