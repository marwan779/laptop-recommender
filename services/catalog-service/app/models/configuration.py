import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class LaptopConfigurationAlias(Base):
    __tablename__ = "laptop_configuration_alias"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.id"))
    external_id: Mapped[str] = mapped_column(String)
    alias_type: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    canonical_configuration = relationship("LaptopConfiguration", back_populates="aliases")


class LaptopMemory(Base):
    __tablename__ = "laptop_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    memory_module_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memory_module.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    is_soldered: Mapped[bool] = mapped_column(Boolean)
    slot_count: Mapped[int | None] = mapped_column(Integer)
    max_supported_gb: Mapped[int | None] = mapped_column(Integer)


class LaptopStorage(Base):
    __tablename__ = "laptop_storage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    storage_device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_device.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    is_primary: Mapped[bool] = mapped_column(Boolean)


class LaptopStorageSlot(Base):
    __tablename__ = "laptop_storage_slot"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    slot_type: Mapped[str] = mapped_column(String)
    interface: Mapped[str] = mapped_column(String)
    occupied: Mapped[bool] = mapped_column(Boolean)
    supports_upgrade: Mapped[bool] = mapped_column(Boolean)


class Battery(Base):
    __tablename__ = "battery"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    capacity_wh: Mapped[float | None] = mapped_column(Numeric)
    cells: Mapped[int | None] = mapped_column(Integer)
    measured_runtime_h: Mapped[float | None] = mapped_column(Numeric)
    runtime_source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_source.id"))


class LaptopConnectivity(Base):
    __tablename__ = "laptop_connectivity"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    wifi_standard: Mapped[str | None] = mapped_column(String)
    bluetooth_version: Mapped[str | None] = mapped_column(String)
    ethernet: Mapped[bool | None] = mapped_column(Boolean)
    ethernet_speed: Mapped[str | None] = mapped_column(String)
    has_hdmi: Mapped[bool | None] = mapped_column(Boolean)
    has_displayport: Mapped[bool | None] = mapped_column(Boolean)
    has_sd_card_reader: Mapped[bool | None] = mapped_column(Boolean)
    has_headphone_jack: Mapped[bool | None] = mapped_column(Boolean)


class LaptopPort(Base):
    __tablename__ = "laptop_port"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    port_type: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)
    version: Mapped[str | None] = mapped_column(String)
    supports_power_delivery: Mapped[bool | None] = mapped_column(Boolean)
    supports_display_output: Mapped[bool | None] = mapped_column(Boolean)


class LaptopBuild(Base):
    __tablename__ = "laptop_build"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    material: Mapped[str | None] = mapped_column(String)
    chassis_material: Mapped[str | None] = mapped_column(String)
    hinge_material: Mapped[str | None] = mapped_column(String)
    military_standard: Mapped[str | None] = mapped_column(String)
    durability_rating: Mapped[str | None] = mapped_column(String)


class LaptopMeasurement(Base):
    __tablename__ = "laptop_measurement"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    weight_kg: Mapped[float | None] = mapped_column(Numeric)
    length_mm: Mapped[float | None] = mapped_column(Numeric)
    width_mm: Mapped[float | None] = mapped_column(Numeric)
    height_mm: Mapped[float | None] = mapped_column(Numeric)


class LaptopThermals(Base):
    __tablename__ = "laptop_thermals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    cpu_load_temp_c: Mapped[float | None] = mapped_column(Numeric)
    gpu_load_temp_c: Mapped[float | None] = mapped_column(Numeric)
    surface_temp_c: Mapped[float | None] = mapped_column(Numeric)
    fan_noise_db: Mapped[float | None] = mapped_column(Numeric)
    idle_noise_db: Mapped[float | None] = mapped_column(Numeric)
    sustained_performance: Mapped[float | None] = mapped_column(Numeric)
    throttling_observed: Mapped[bool | None] = mapped_column(Boolean)


class LaptopAudio(Base):
    __tablename__ = "laptop_audio"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    speaker_quality: Mapped[str | None] = mapped_column(String)
    speaker_loudness_db: Mapped[float | None] = mapped_column(Numeric)
    microphone_quality: Mapped[str | None] = mapped_column(String)
    headphone_output_quality: Mapped[str | None] = mapped_column(String)


class LaptopWebcam(Base):
    __tablename__ = "laptop_webcam"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laptop_configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laptop_configuration.id"))
    resolution: Mapped[str | None] = mapped_column(String)
    megapixels: Mapped[float | None] = mapped_column(Numeric)
    has_ir: Mapped[bool | None] = mapped_column(Boolean)
    has_privacy_shutter: Mapped[bool | None] = mapped_column(Boolean)


__all__ = [
    "LaptopConfigurationAlias",
    "LaptopMemory",
    "LaptopStorage",
    "LaptopStorageSlot",
    "Battery",
    "LaptopConnectivity",
    "LaptopPort",
    "LaptopBuild",
    "LaptopMeasurement",
    "LaptopThermals",
    "LaptopAudio",
    "LaptopWebcam",
]

