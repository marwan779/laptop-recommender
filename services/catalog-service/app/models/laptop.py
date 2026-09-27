import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
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
    manufacturer_part_number: Mapped[str | None] = mapped_column(String)
    identity_hash: Mapped[str] = mapped_column(String, unique=True)

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


__all__ = [
    "Brand",
    "LaptopFamily",
    "LaptopModel",
    "LaptopConfiguration",
]

