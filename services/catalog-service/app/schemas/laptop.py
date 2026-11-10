import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class LaptopOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    store_name: str
    retailer_sku: str | None = None
    price_egp: float
    in_stock: bool
    offer_url: str | None = None
    last_checked_at: datetime | str | None = None


class LaptopCategoryScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    usage_category_id: uuid.UUID
    score: float
    raw_percentile: float | None = None
    confidence: float | None = None
    notes: str | None = None


class LaptopConfigurationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_id: str | None = None
    manufacturer_part_number: str | None = None
    title: str | None = None
    thumbnail_url: str | None = None
    min_price_egp: float | None = None
    max_price_egp: float | None = None
    cheapest_store: str | None = None
    price_spread_egp: float | None = None
    stores_count: int = 1
    hardware_score: float | None = None
    portability_score: float | None = None
    battery_hours_estimate: float | None = None
    upgradeability_score: float | None = None


class LaptopConfigurationDetail(LaptopConfigurationSummary):
    offers: list[LaptopOfferRead] = []
    category_scores: list[LaptopCategoryScoreRead] = []


class CatalogListItemResponse(BaseModel):
    """Compact catalog card payload with pricing, key specs, and review intelligence."""

    id: str
    canonical_id: str
    mpn: str | None = None
    brand: str
    laptop_family: str | None = None
    laptop_model: str
    title: str
    thumbnail_url: str | None = None

    min_price_egp: float
    cheapest_store: str
    in_stock: bool = True
    stores_count: int = 1

    ram_capacity_gb: int
    storage_capacity_gb: int
    gpu_model: str
    cpu_model: str
    display_size_inches: float

    community_nlp_score: float = 75.0
    value_score: float = 50.0
    has_reviews: bool = False
    reviews_evidence_count: int = 0

    pros_ar: list[str] = Field(default_factory=list)
    pros_en: list[str] = Field(default_factory=list)
    cons_ar: list[str] = Field(default_factory=list)
    cons_en: list[str] = Field(default_factory=list)

    metric_scores: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Optional 0-100 metric scores used by real-world/performance filters "
            "(acoustics, thermals, battery, build, keyboard, cpu, gpu, display)."
        ),
    )


class PageInfo(BaseModel):
    """Cursor (keyset) pagination metadata for one catalog slice."""

    has_next_page: bool = False
    has_previous_page: bool = False
    start_cursor: str | None = Field(
        default=None,
        description="Opaque cursor pointing at the first item of this slice.",
    )
    end_cursor: str | None = Field(
        default=None,
        description="Opaque cursor pointing at the last item of this slice.",
    )


class CatalogListResponse(BaseModel):
    """Cursor-paginated catalog browse response."""

    total: int
    limit: int
    page_info: PageInfo
    items: list[CatalogListItemResponse] = Field(default_factory=list)


# =============================================================================
# DETAILED SPECIFICATION SCHEMAS FOR FULL UX VIEW
# =============================================================================


class CpuSpecDetail(BaseModel):
    """Deep CPU specifications."""

    manufacturer: str
    line: str | None = None
    model: str
    series: str | None = None
    full_name: str | None = None
    cores: int
    threads: int
    clock_base_ghz: float | None = None
    clock_boost_ghz: float | None = None
    cache_mb: int | None = None
    base_power_w: int | None = None
    npu_tops: float | None = None
    microarchitecture: str | None = None


class GpuSpecDetail(BaseModel):
    """Deep GPU specifications."""

    manufacturer: str
    model: str
    variant: str | None = None
    vram_gb: int | None = None
    vram_type: str | None = None
    tdp_w: int | None = None
    integrated: bool = False
    ai_tops: int | None = None
    igpu_model: str | None = None


class MemorySpecDetail(BaseModel):
    """Deep Memory (RAM) specifications."""

    capacity_gb: int
    memory_type: str
    speed_mhz: int | None = None
    slot_count: int | None = None
    max_supported_gb: int | None = None
    is_soldered: bool = False
    channels: str | None = None


class StorageSpecDetail(BaseModel):
    """Deep Storage specifications."""

    capacity_gb: int
    storage_type: str = "SSD"
    interface: str | None = None
    slot_count: int | None = None


class DisplaySpecDetail(BaseModel):
    """Deep Display specifications."""

    size_inches: float
    resolution: str
    width: int
    height: int
    panel_type: str | None = None
    refresh_rate_hz: int = 60
    aspect_ratio: str | None = "16:9"
    brightness_nits: int | None = None
    color_gamut: str | None = None
    touchscreen: bool = False
    hdr: bool = False


class PowerBatterySpecDetail(BaseModel):
    """Deep Power and Battery specifications."""

    battery_capacity_wh: float | None = None
    battery_cells: int | None = None
    power_adapter_w: float | None = None
    fast_charging: bool = False
    usb_c_pd_charging: bool = False


class PhysicalSpecDetail(BaseModel):
    """Physical dimensions and chassis measurements."""

    weight_kg: float | None = None
    width_mm: float | None = None
    depth_mm: float | None = None
    height_mm: float | None = None


class BuildSecuritySpecDetail(BaseModel):
    """Chassis build, keyboard, and biometric security features."""

    has_backlit_keyboard: bool = False
    keyboard_backlight_type: str | None = None
    has_fingerprint: bool = False
    has_copilot_key: bool = False
    security_features: list[str] = Field(default_factory=list)


class AudioWebcamSpecDetail(BaseModel):
    """Sound system and webcam specifications."""

    speaker_count: int = 2
    audio_system: str | None = None
    webcam_resolution: str | None = None
    has_ir_camera: bool = False
    has_privacy_shutter: bool = False


class ConnectivityOsSpecDetail(BaseModel):
    """Networking, ports, and operating system."""

    wifi: str | None = None
    bluetooth: str | None = None
    has_ethernet: bool = False
    ethernet_speed: str | None = None
    has_card_reader: bool = False
    operating_system: str | None = None
    ports: list[str] = Field(default_factory=list)


class HardwareMetricsDetail(BaseModel):
    """11 normalized performance scores and operational tiers."""

    cpu_score: float
    gpu_score: float
    silicon_index: float | None = None
    power_therm_score: float
    display_score: float
    mobility_score: float
    longevity_score: float
    ergonomics_score: float
    connectivity_score: float
    community_nlp_score: float | None = None
    thermals_score: float | None = None
    acoustics_score: float | None = None
    build_and_hinges_score: float | None = None
    keyboard_and_trackpad_score: float | None = None
    real_battery_and_reliability_score: float | None = None
    value_score: float
    effective_price_egp: float
    estimated_battery_hours: float | None = None
    silicon_tier: str | None = None
    display_tier: str | None = None
    portability_tier: str | None = None
    upgradeability_tier: str | None = None


class DetailedOfferRead(BaseModel):
    """Store-specific listing details with live prices and product URLs."""

    id: str | None = None
    store_key: str
    store_name: str
    store_domain: str | None = None
    product_url: str
    retailer_sku: str | None = None
    mpn: str | None = None
    price_egp: float
    previous_price_egp: float | None = None
    in_stock: bool = True
    is_valid_price: bool = True
    is_cheapest: bool = False
    price_updated_at: datetime | str | None = None
    last_checked_at: datetime | str | None = None


class FullLaptopDetailResponse(BaseModel):
    """Comprehensive, 35+ dimension laptop detail payload for frontend product pages."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    canonical_id: str
    mpn: str | None = None
    brand: str
    laptop_family: str | None = None
    laptop_model: str
    title: str
    thumbnail_url: str | None = None
    base_color: str | None = None
    color: str | None = None
    form_factor: str = "Clamshell"
    market_positioning: str | None = None
    release_year: int | None = None
    warranty: str | None = None
    warranty_years: int | None = None

    # Aggregated Market Pricing
    min_price_egp: float
    max_price_egp: float | None = None
    previous_min_price_egp: float | None = None
    cheapest_store: str
    cheapest_offer_url: str | None = None
    price_spread_egp: float | None = None
    stores_count: int = 1
    in_stock: bool = True
    price_updated_at: datetime | str | None = None
    price_checked_at: datetime | str | None = None
    available_stores: list[str] = Field(default_factory=list)
    prices_by_store: dict[str, float] = Field(default_factory=dict)
    urls_by_store: dict[str, str] = Field(default_factory=dict)
    offers: list[DetailedOfferRead] = Field(default_factory=list)

    # 35+ Structured Hardware Dimensions
    cpu: CpuSpecDetail
    gpu: GpuSpecDetail
    memory: MemorySpecDetail
    storage: StorageSpecDetail
    display: DisplaySpecDetail
    power_battery: PowerBatterySpecDetail
    physical: PhysicalSpecDetail
    build_security: BuildSecuritySpecDetail
    audio_webcam: AudioWebcamSpecDetail
    connectivity_os: ConnectivityOsSpecDetail

    # Normalized 1:1 TOPSIS Metrics
    metrics: HardwareMetricsDetail | None = None

    # Community Review Intelligence
    reviews_evidence_count: int = 0
    pros_en: list[str] = Field(default_factory=list)
    pros_ar: list[str] = Field(default_factory=list)
    cons_en: list[str] = Field(default_factory=list)
    cons_ar: list[str] = Field(default_factory=list)

    # Human-Grade Explainable Badges
    why_recommended_ar: list[str] = Field(default_factory=list)
    why_recommended_en: list[str] = Field(default_factory=list)
