from datetime import datetime
from enum import StrEnum
import uuid

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class InboxStatus(StrEnum):
    """Lifecycle state of a consumed inbox message."""

    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class InboxMessage(Base):
    """Transactional inbox record preventing duplicate event processing.

    Rows are inserted inside the same database transaction that applies the
    business change, so an inbox entry exists only when its handler committed.
    """

    __tablename__ = "inbox_message"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    handler_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=InboxStatus.PROCESSED, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["InboxMessage", "InboxStatus"]
