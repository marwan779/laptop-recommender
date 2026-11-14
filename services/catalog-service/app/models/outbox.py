from datetime import datetime
from enum import StrEnum
import uuid

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class OutboxStatus(StrEnum):
    """Lifecycle state of an outbox message."""

    PENDING = "PENDING"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class OutboxMessage(Base):
    """Transactional outbox message entity ensuring guaranteed at-least-once message delivery."""

    __tablename__ = "outbox_message"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    routing_key: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, default=OutboxStatus.PENDING, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["OutboxStatus", "OutboxMessage"]
