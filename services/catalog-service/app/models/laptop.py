import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.metrics import LaptopMetrics
    from app.models.offer import LaptopOffer


class LaptopConfiguration(Base):
    """Canonical laptop configuration entity storing complete hardware specifications,

    aggregated pricing, and lifecycle timestamps as strongly-typed SQL columns.
    """

    __tablename__ = "laptop_configuration"
    __table_args__ = (
        Index("ix_laptop_cursor_price_id", "min_price_egp", "id"),
    )

    # Identity & Presentation
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    mpn: Mapped[str | None] = mapped_column(String(100), index=True)
    brand: Mapped[str] = mapped_column(String(50), index=True)
    laptop_family: Mapped[str | None] = mapped_column(String(100), index=True)
    laptop_model: Mapped[str] = mapped_column(String(150), index=True)
    title: Mapped[str] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    base_color: Mapped[str | None] = mapped_column(String(50))
    color: Mapped[str | None] = mapped_column(String(50))
    form_factor: Mapped[str] = mapped_column(String(50), default="Clamshell")
    market_positioning: Mapped[str | None] = mapped_column(String(50))
    release_year: Mapped[int | None] = mapped_column(Integer)
    warranty: Mapped[str | None] = mapped_column(String(100))
    warranty_years: Mapped[int | None] = mapped_column(Integer)
    is_bundle: Mapped[bool] = mapped_column(Boolean, default=False)

    # CPU Specifications
    cpu_manufacturer: Mapped[str] = mapped_column(String(50))
    cpu_line: Mapped[str | None] = mapped_column(String(50))
    cpu_model: Mapped[str] = mapped_column(String(100), index=True)
    cpu_series: Mapped[str | None] = mapped_column(String(50))
    cpu_full_name: Mapped[str | None] = mapped_column(String(120))
    cpu_cores: Mapped[int] = mapped_column(Integer)
    cpu_threads: Mapped[int] = mapped_column(Integer)
    cpu_base_clock_ghz: Mapped[float | None] = mapped_column(Numeric(4, 2))
    cpu_boost_clock_ghz: Mapped[float | None] = mapped_column(Numeric(4, 2))
    cpu_cache_mb: Mapped[int | None] = mapped_column(Integer)
    cpu_base_power_w: Mapped[int | None] = mapped_column(Integer)
    cpu_npu_tops: Mapped[float | None] = mapped_column(Numeric(6, 2))
    cpu_microarchitecture: Mapped[str | None] = mapped_column(String(50))

    # GPU Specifications
    gpu_manufacturer: Mapped[str] = mapped_column(String(50))
    gpu_model: Mapped[str] = mapped_column(String(100), index=True)
    gpu_variant: Mapped[str | None] = mapped_column(String(50))
    gpu_vram_gb: Mapped[int | None] = mapped_column(Integer)
    gpu_vram_type: Mapped[str | None] = mapped_column(String(20))
    gpu_tdp_w: Mapped[int | None] = mapped_column(Integer)
    gpu_integrated: Mapped[bool] = mapped_column(Boolean, default=False)
    gpu_ai_tops: Mapped[int | None] = mapped_column(Integer)
    gpu_igpu_model: Mapped[str | None] = mapped_column(String(100))

    # Memory (RAM)
    ram_capacity_gb: Mapped[int] = mapped_column(Integer, index=True)
    ram_type: Mapped[str] = mapped_column(String(20))
    ram_speed_mhz: Mapped[int | None] = mapped_column(Integer)
    ram_slot_count: Mapped[int | None] = mapped_column(Integer)
    ram_max_supported_gb: Mapped[int | None] = mapped_column(Integer)
    ram_is_soldered: Mapped[bool] = mapped_column(Boolean, default=False)
    ram_channels: Mapped[str | None] = mapped_column(String(30))

    # Storage
    storage_capacity_gb: Mapped[int] = mapped_column(Integer, index=True)
    storage_type: Mapped[str] = mapped_column(String(20), default="SSD")
    storage_interface: Mapped[str | None] = mapped_column(String(50))
    storage_slot_count: Mapped[int | None] = mapped_column(Integer)

    # Display
    display_size_inches: Mapped[float] = mapped_column(Numeric(4, 1), index=True)
    display_resolution: Mapped[str] = mapped_column(String(30))
    display_width: Mapped[int] = mapped_column(Integer)
    display_height: Mapped[int] = mapped_column(Integer)
    display_panel_type: Mapped[str | None] = mapped_column(String(30))
    display_refresh_rate_hz: Mapped[int] = mapped_column(Integer, default=60, index=True)
    display_aspect_ratio: Mapped[str | None] = mapped_column(String(20), default="16:9")
    display_brightness_nits: Mapped[int | None] = mapped_column(Integer)
    display_color_gamut: Mapped[str | None] = mapped_column(String(50))
    display_touchscreen: Mapped[bool] = mapped_column(Boolean, default=False)
    display_hdr: Mapped[bool] = mapped_column(Boolean, default=False)

    # Power & Battery
    battery_capacity_wh: Mapped[float | None] = mapped_column(Numeric(6, 2))
    battery_cells: Mapped[int | None] = mapped_column(Integer)
    power_adapter_w: Mapped[float | None] = mapped_column(Numeric(6, 2))
    fast_charging: Mapped[bool] = mapped_column(Boolean, default=False)
    usb_c_pd_charging: Mapped[bool] = mapped_column(Boolean, default=False)

    # Physical Dimensions
    weight_kg: Mapped[float | None] = mapped_column(Numeric(4, 2), index=True)
    width_mm: Mapped[float | None] = mapped_column(Numeric(6, 2))
    depth_mm: Mapped[float | None] = mapped_column(Numeric(6, 2))
    height_mm: Mapped[float | None] = mapped_column(Numeric(6, 2))

    # Build, Audio & Webcam
    has_backlit_keyboard: Mapped[bool] = mapped_column(Boolean, default=False)
    keyboard_backlight_type: Mapped[str | None] = mapped_column(String(50))
    has_fingerprint: Mapped[bool] = mapped_column(Boolean, default=False)
    has_copilot_key: Mapped[bool] = mapped_column(Boolean, default=False)
    security_features: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    speaker_count: Mapped[int] = mapped_column(Integer, default=2)
    audio_system: Mapped[str | None] = mapped_column(String(50))
    webcam_resolution: Mapped[str | None] = mapped_column(String(30))
    has_ir_camera: Mapped[bool] = mapped_column(Boolean, default=False)
    has_privacy_shutter: Mapped[bool] = mapped_column(Boolean, default=False)

    # Connectivity & OS
    wifi: Mapped[str | None] = mapped_column(String(50))
    bluetooth: Mapped[str | None] = mapped_column(String(50))
    has_ethernet: Mapped[bool] = mapped_column(Boolean, default=False)
    ethernet_speed: Mapped[str | None] = mapped_column(String(30))
    has_card_reader: Mapped[bool] = mapped_column(Boolean, default=False)
    operating_system: Mapped[str | None] = mapped_column(String(50))
    ports: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    # Aggregated Pricing & Stock Availability
    min_price_egp: Mapped[float] = mapped_column(Numeric(12, 2), index=True)
    max_price_egp: Mapped[float | None] = mapped_column(Numeric(12, 2))
    previous_min_price_egp: Mapped[float | None] = mapped_column(Numeric(12, 2))
    cheapest_store: Mapped[str] = mapped_column(String(50))
    price_spread_egp: Mapped[float | None] = mapped_column(Numeric(12, 2))
    stores_count: Mapped[int] = mapped_column(Integer, default=1)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    available_stores: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    # Business Lifecycle & Freshness Timestamps
    laptop_added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    price_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    price_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    # Community Reviews Lifecycle
    has_reviews: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reviews_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    reviews_evidence_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pros_en: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    pros_ar: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    cons_en: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    cons_ar: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")

    # DB Metadata Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    metrics: Mapped["LaptopMetrics"] = relationship(
        "LaptopMetrics", back_populates="laptop", uselist=False, cascade="all, delete-orphan"
    )
    offers: Mapped[list["LaptopOffer"]] = relationship(
        "LaptopOffer", back_populates="configuration", cascade="all, delete-orphan"
    )


__all__ = ["LaptopConfiguration"]
