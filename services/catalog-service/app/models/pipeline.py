import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class SpecificationEvidence(Base):
    __tablename__ = "specification_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.id"))

    field_name: Mapped[str] = mapped_column(String)
    field_value: Mapped[str] = mapped_column(Text)

    source_url: Mapped[str | None] = mapped_column(Text)
    source_identifier: Mapped[str | None] = mapped_column(String)

    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[str | None] = mapped_column(String)


class RawLaptopRecord(Base):
    __tablename__ = "raw_laptop_record"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.id"))
    external_id: Mapped[str] = mapped_column(String)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processing_status: Mapped[str] = mapped_column(String)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


__all__ = [
    "SpecificationEvidence",
    "RawLaptopRecord",
]

