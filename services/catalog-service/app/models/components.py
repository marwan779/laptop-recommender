import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class CPU(Base):
    __tablename__ = "cpu"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manufacturer: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    architecture: Mapped[str] = mapped_column(String)
    generation: Mapped[str | None] = mapped_column(String)
    cores: Mapped[int | None] = mapped_column(Integer)
    performance_cores: Mapped[int | None] = mapped_column(Integer)
    efficiency_cores: Mapped[int | None] = mapped_column(Integer)
    threads: Mapped[int | None] = mapped_column(Integer)
    base_clock_ghz: Mapped[float | None] = mapped_column(Numeric)
    boost_clock_ghz: Mapped[float | None] = mapped_column(Numeric)
    tdp_w: Mapped[float | None] = mapped_column(Numeric)
    benchmark_score: Mapped[float | None] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class GPU(Base):
    __tablename__ = "gpu"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manufacturer: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    architecture: Mapped[str | None] = mapped_column(String)
    vram_gb: Mapped[float | None] = mapped_column(Numeric)
    memory_type: Mapped[str | None] = mapped_column(String)
    tdp_w: Mapped[float | None] = mapped_column(Numeric)
    integrated: Mapped[bool] = mapped_column(Boolean)
    benchmark_score: Mapped[float | None] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Display(Base):
    __tablename__ = "display"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    size_inches: Mapped[float] = mapped_column(Numeric)
    resolution_width: Mapped[int] = mapped_column(Integer)
    resolution_height: Mapped[int] = mapped_column(Integer)
    panel_type: Mapped[str | None] = mapped_column(String)
    refresh_rate_hz: Mapped[int | None] = mapped_column(Integer)
    aspect_ratio: Mapped[str | None] = mapped_column(String)
    brightness_nits: Mapped[int | None] = mapped_column(Integer)
    color_gamut: Mapped[str | None] = mapped_column(String)
    srgb_coverage: Mapped[float | None] = mapped_column(Numeric)
    dci_p3_coverage: Mapped[float | None] = mapped_column(Numeric)
    response_time_ms: Mapped[float | None] = mapped_column(Numeric)
    touchscreen: Mapped[bool | None] = mapped_column(Boolean)
    oled: Mapped[bool] = mapped_column(Boolean)
    hdr: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MemoryModule(Base):
    __tablename__ = "memory_module"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_type: Mapped[str] = mapped_column(String)
    speed_mhz: Mapped[int | None] = mapped_column(Integer)
    capacity_gb: Mapped[int] = mapped_column(Integer)
    form_factor: Mapped[str | None] = mapped_column(String)


class StorageDevice(Base):
    __tablename__ = "storage_device"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String)
    interface: Mapped[str | None] = mapped_column(String)
    capacity_gb: Mapped[int] = mapped_column(Integer)
    form_factor: Mapped[str | None] = mapped_column(String)
    model_name: Mapped[str | None] = mapped_column(String)


class DataSource(Base):
    __tablename__ = "data_source"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String)
    base_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageCategory(Base):
    __tablename__ = "usage_category"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String)


__all__ = [
    "CPU",
    "GPU",
    "Display",
    "MemoryModule",
    "StorageDevice",
    "DataSource",
    "UsageCategory",
]

