import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
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


class OfferPriceHistory(Base):
    """Append-only event log of price and stock changes for a store offer.

    A row is written only when a price changes by at least 1.0 EGP or the stock
    state flips, keeping each offer's piecewise-constant price step function
    storage-efficient while remaining plottable to the present.
    """

    __tablename__ = "offer_price_history"
    __table_args__ = (
        Index(
            "ix_offer_price_history_laptop_time",
            "laptop_configuration_id",
            "recorded_at",
        ),
        Index(
            "ix_offer_price_history_offer_time",
            "offer_id",
            "recorded_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laptop_offer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalized FK so all store curves for one laptop are a single index scan.
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laptop_configuration.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    store_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    price_egp: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


__all__ = ["LaptopOffer", "OfferPriceHistory"]
