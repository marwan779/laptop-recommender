import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.laptop import LaptopConfiguration


class LaptopMetrics(Base):
    """Normalized 1:1 hardware performance scores, thermal metrics, and TOPSIS inputs.

    Stores pure numeric floats (0.00 to 100.00) for instant NumPy matrix extraction.
    """

    __tablename__ = "laptop_metrics"

    laptop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("laptop_configuration.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # 11 Flat TOPSIS Float Scores (0.00 to 100.00)
    cpu_score: Mapped[float] = mapped_column(Numeric(5, 2))
    gpu_score: Mapped[float] = mapped_column(Numeric(5, 2))
    silicon_index: Mapped[float] = mapped_column(Numeric(5, 2))
    power_therm_score: Mapped[float] = mapped_column(Numeric(5, 2))
    display_score: Mapped[float] = mapped_column(Numeric(5, 2))
    mobility_score: Mapped[float] = mapped_column(Numeric(5, 2))
    longevity_score: Mapped[float] = mapped_column(Numeric(5, 2))
    ergonomics_score: Mapped[float] = mapped_column(Numeric(5, 2))
    connectivity_score: Mapped[float] = mapped_column(Numeric(5, 2))
    community_nlp_score: Mapped[float] = mapped_column(Numeric(5, 2))
    value_score: Mapped[float] = mapped_column(Numeric(5, 2))

    # Operational Meta for TOPSIS Recommender
    effective_price_egp: Mapped[float] = mapped_column(Numeric(12, 2))
    is_recommendable_price: Mapped[bool] = mapped_column(Boolean, default=True)
    in_stock_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Computed Sub-Metrics & Tiers
    delta_p_watts: Mapped[float] = mapped_column(Numeric(6, 2))
    simultaneous_load_w: Mapped[float] = mapped_column(Numeric(6, 2))
    electrical_status: Mapped[str] = mapped_column(String(30))
    estimated_battery_hours: Mapped[float] = mapped_column(Numeric(4, 2))
    silicon_tier: Mapped[str] = mapped_column(String(50))
    display_tier: Mapped[str] = mapped_column(String(50))
    portability_tier: Mapped[str] = mapped_column(String(30))
    upgradeability_tier: Mapped[str] = mapped_column(String(50))
    is_copilot_plus_pc: Mapped[bool] = mapped_column(Boolean, default=False)
    pricing_status: Mapped[str] = mapped_column(String(30))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationship back to laptop
    laptop: Mapped["LaptopConfiguration"] = relationship("LaptopConfiguration", back_populates="metrics")


__all__ = ["LaptopMetrics"]
