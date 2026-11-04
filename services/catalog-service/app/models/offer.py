import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.laptop import LaptopConfiguration


class LaptopOffer(Base):
    """Store-specific product listing and pricing offer for a canonical laptop configuration."""

    __tablename__ = "laptop_offer"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laptop_configuration.id", ondelete="CASCADE"),
        index=True,
    )
    store_key: Mapped[str] = mapped_column(String(50), index=True)
    store_name: Mapped[str] = mapped_column(String(100))
    store_domain: Mapped[str | None] = mapped_column(String(100))
    product_url: Mapped[str] = mapped_column(Text)
    retailer_sku: Mapped[str | None] = mapped_column(String(100))
    mpn: Mapped[str | None] = mapped_column(String(100))
    price_egp: Mapped[float] = mapped_column(Numeric(12, 2), index=True)
    previous_price_egp: Mapped[float | None] = mapped_column(Numeric(12, 2))
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_valid_price: Mapped[bool] = mapped_column(Boolean, default=True)

    # Freshness & Tracking
    price_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    configuration: Mapped["LaptopConfiguration"] = relationship("LaptopConfiguration", back_populates="offers")


__all__ = ["LaptopOffer"]
