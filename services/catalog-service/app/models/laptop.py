import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class Brand(Base):
    __tablename__ = "brand"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String)
    website_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    families = relationship("LaptopFamily", back_populates="brand")


class LaptopFamily(Base):
    __tablename__ = "laptop_family"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brand.id"))
    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    brand = relationship("Brand", back_populates="families")
    models = relationship("LaptopModel", back_populates="family")


class LaptopModel(Base):
    __tablename__ = "laptop_model"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_family.id"))
    manufacturer_model: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    family = relationship("LaptopFamily", back_populates="models")
    configurations = relationship("LaptopConfiguration", back_populates="model")


class LaptopConfiguration(Base):
    __tablename__ = "laptop_configuration"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_model.id"))
    canonical_id: Mapped[str | None] = mapped_column(String, index=True)
    manufacturer_part_number: Mapped[str | None] = mapped_column(String, index=True)
    identity_hash: Mapped[str] = mapped_column(String, unique=True)

    # Core presentation & price aggregation
    title: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    min_price_egp: Mapped[float | None] = mapped_column(Numeric, index=True)
    max_price_egp: Mapped[float | None] = mapped_column(Numeric)
    cheapest_store: Mapped[str | None] = mapped_column(String)
    price_spread_egp: Mapped[float | None] = mapped_column(Numeric)
    stores_count: Mapped[int] = mapped_column(Integer, default=1)

    # Deterministic composite scores
    hardware_score: Mapped[float | None] = mapped_column(Numeric, index=True)
    portability_score: Mapped[float | None] = mapped_column(Numeric)
    battery_hours_estimate: Mapped[float | None] = mapped_column(Numeric)
    upgradeability_score: Mapped[float | None] = mapped_column(Numeric)

    cpu_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cpu.id"))
    gpu_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("gpu.id"))
    display_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("display.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    model = relationship("LaptopModel", back_populates="configurations")
    cpu = relationship("CPU")
    gpu = relationship("GPU")
    display = relationship("Display")
    aliases = relationship("LaptopConfigurationAlias", back_populates="canonical_configuration")

    # Live store offers & persona alignment scores
    offers = relationship("LaptopOffer", back_populates="configuration", cascade="all, delete-orphan")
    category_scores = relationship("LaptopCategoryScore", back_populates="configuration", cascade="all, delete-orphan")


__all__ = [
    "Brand",
    "LaptopFamily",
    "LaptopModel",
    "LaptopConfiguration",
]
