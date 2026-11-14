"""Outbox Repository for Transactional Outbox Pattern.

Encapsulates SQL persistence, atomic leasing with row locking, and lifecycle
state transitions for outbox messages.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
import json
from typing import Any
import uuid

from pydantic import BaseModel
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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

        outbox_id = message_id or uuid.uuid4()
        event_id = self._extract_event_id(payload) or str(outbox_id)

        msg = OutboxMessage(
            id=outbox_id,
            event_id=event_id,
            event_type=event_type,
            routing_key=routing_key,
            payload_json=payload_json,
            status=OutboxStatus.PENDING,
            retry_count=0,
            max_retries=max_retries,
            last_error=None,
            correlation_id=correlation_id or str(uuid.uuid4()),
            created_at=datetime.now(UTC),
            leased_at=None,
            published_at=None,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    @staticmethod
    def _extract_event_id(payload: BaseModel | dict[str, Any] | str) -> str | None:
        """Read the domain event id from the payload so inbox and outbox agree."""
        if isinstance(payload, BaseModel):
            value = getattr(payload, "event_id", None)
            return str(value) if value else None
        if isinstance(payload, dict):
            value = payload.get("event_id")
            return str(value) if value else None
        if isinstance(payload, str):
            try:
                decoded = json.loads(payload)
            except (TypeError, ValueError):
                return None
            if isinstance(decoded, dict) and decoded.get("event_id"):
                return str(decoded["event_id"])
        return None

    async def claim_batch(
        self,
        batch_size: int | None = None,
        lease_duration_minutes: int | None = None,
    ) -> Sequence[OutboxMessage]:
        """Claim a batch of deliverable messages using SKIP LOCKED.

        Pending messages are claimed immediately. Messages stuck in
        ``PUBLISHING`` whose lease has expired are re-claimed (self-healing from
        a crashed relay), incrementing their retry count so poison messages
        still exhaust ``max_retries`` instead of looping forever.
        """
        resolved_batch_size = batch_size if batch_size is not None else settings.outbox_batch_size
        resolved_lease_minutes = (
            lease_duration_minutes
            if lease_duration_minutes is not None
            else settings.outbox_lease_duration_minutes
        )

        now = datetime.now(UTC)
        stale_threshold = now - timedelta(minutes=resolved_lease_minutes)

        stmt = (
            select(OutboxMessage)
            .where(
                OutboxMessage.retry_count < OutboxMessage.max_retries,
                or_(
                    OutboxMessage.status == OutboxStatus.PENDING,
                    and_(
                        OutboxMessage.status == OutboxStatus.PUBLISHING,
                        or_(
                            OutboxMessage.leased_at.is_(None),
                            OutboxMessage.leased_at < stale_threshold,
                        ),
                    ),
                ),
            )
            .order_by(OutboxMessage.created_at.asc())
            .limit(resolved_batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        messages = result.scalars().all()

        for msg in messages:
            if msg.status == OutboxStatus.PUBLISHING and (
                msg.leased_at is None or msg.leased_at < stale_threshold
            ):
                msg.retry_count += 1
                msg.last_error = (
                    f"Reclaimed zombie message after lease expired ({resolved_lease_minutes}m)"
                )
            msg.status = OutboxStatus.PUBLISHING
            msg.leased_at = now

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
                leased_at=None,
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
        msg.leased_at = None

        if msg.retry_count >= msg.max_retries:
            msg.status = OutboxStatus.FAILED
        else:
            msg.status = OutboxStatus.PENDING

        await self.session.flush()
        return msg
