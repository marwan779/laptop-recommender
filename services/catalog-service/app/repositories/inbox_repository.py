"""Inbox Repository implementing the Transactional Inbox Pattern.

The claim is an atomic ``INSERT ... ON CONFLICT DO NOTHING``. Because the
insert participates in the caller's transaction, committing business changes
and claiming the message id succeed or fail together.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbox import InboxMessage, InboxStatus
from app.repositories.base import BaseRepository


class InboxRepository(BaseRepository[InboxMessage]):
    """Repository handling idempotent inbox claims for consumed events."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(InboxMessage, session)

    async def claim_message(
        self,
        message_id: str,
        event_type: str,
        handler_name: str,
    ) -> bool:
        """Attempt to claim a message id.

        Returns:
            True when this handler owns the message, False when a row for the
            same message id already exists (duplicate delivery).
        """
        stmt = (
            insert(InboxMessage)
            .values(
                message_id=message_id,
                event_type=event_type,
                handler_name=handler_name,
                status=InboxStatus.PROCESSED,
            )
            .on_conflict_do_nothing(index_elements=[InboxMessage.message_id])
            .returning(InboxMessage.message_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
