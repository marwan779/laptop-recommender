"""Canonical laptop review source links (videos, community threads, editorial reviews)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.laptop import LaptopConfiguration


class LaptopReviewSource(Base):
    """A single external review source attached to a canonical laptop configuration."""

    __tablename__ = "laptop_review_source"
    __table_args__ = (
        UniqueConstraint(
            "laptop_configuration_id",
            "url",
            name="uq_laptop_review_source_config_url",
        ),
        Index(
            "ix_laptop_review_source_config_type",
            "laptop_configuration_id",
            "source_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "laptop_configuration.id",
            name="fk_laptop_review_source_config_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    author_or_channel: Mapped[str | None] = mapped_column(String(150), nullable=True)
    channel_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    score_or_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    configuration: Mapped["LaptopConfiguration"] = relationship(
        "LaptopConfiguration",
        back_populates="review_sources",
    )


__all__ = ["LaptopReviewSource"]
