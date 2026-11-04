"""Catalog Database Seeder Repository.

Performs batch identity resolution and strongly-typed upserts for LaptopConfiguration,
LaptopOffer, and LaptopMetrics from scraping catalog payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import re
from typing import Any
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.base import utcnow
from app.models.laptop import LaptopConfiguration
from app.models.metrics import LaptopMetrics
from app.models.offer import LaptopOffer
from app.repositories.base import BaseRepository

logger = logging.getLogger("catalog.repositories.seeder")


@dataclass(frozen=True)
class SeederSummary:
    """Detailed counters describing the outcome of a catalog seeding batch."""

    total_laptops_processed: int
    new_laptops_created: int
    laptops_updated: int
    offers_created: int
    offers_updated: int
    metrics_created: int
    metrics_updated: int


def _safe_int(val: Any, default: int | None = None) -> int | None:
    if val is None:
        return default
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    m = re.search(r"\d+", str(val))
    return int(m.group(0)) if m else default


def _safe_float(val: Any, default: float | None = None) -> float | None:
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"[-+]?\d*\.?\d+", str(val))
    return float(m.group(0)) if m else default


def _safe_bool(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "t")
    return bool(val)


def _safe_str(val: Any, default: str | None = None, max_length: int | None = None) -> str | None:
    if val is None:
        return default
    s = str(val).strip()
    if not s:
        return default
    if max_length and len(s) > max_length:
        return s[:max_length].strip()
    return s


def _safe_list(val: Any) -> list[str]:
    if not val:
        return []
    if isinstance(val, list):
        return [str(item).strip() for item in val if item is not None and str(item).strip()]
    if isinstance(val, str):
        return [s.strip() for s in val.split(",") if s.strip()]
    return []


def _parse_datetime(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


class CatalogSeederRepository(BaseRepository[LaptopConfiguration]):
    """Repository managing batch identity resolution and relational catalog seeding."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(LaptopConfiguration, session)

    async def upsert_catalog(
        self,
        catalog_dict: dict[str, Any],
        batch_size: int = 500,
    ) -> SeederSummary:
        """Upsert an entire catalog of laptops, offers, and metrics into PostgreSQL.

        Args:
            catalog_dict: Parsed catalog dictionary containing a list of 'laptops'.
            batch_size: Chunk size for identity resolution queries.

        Returns:
            SeederSummary with detailed metrics on created vs updated entities.
        """
        raw_laptops = catalog_dict.get("laptops")
        if not isinstance(raw_laptops, list):
            raise ValueError(f"Invalid catalog payload: expected 'laptops' list, got {type(raw_laptops)}")

        total_processed = 0
        new_laptops_count = 0
        updated_laptops_count = 0
        created_offers_count = 0
        updated_offers_count = 0
        created_metrics_count = 0
        updated_metrics_count = 0

        now = utcnow()

        # Step 1: Collect canonical IDs and MPNs for batch lookup
        canonical_ids: list[str] = []
        mpns: list[str] = []

        for item in raw_laptops:
            cid = item.get("canonical_id")
            if cid:
                canonical_ids.append(str(cid).strip())
            mpn = item.get("mpn") or item.get("specs", {}).get("identity", {}).get("manufacturer_part_number")
            if mpn:
                mpns.append(str(mpn).strip())

        # Step 2: Fetch existing configurations in chunks
        existing_by_canonical: dict[str, LaptopConfiguration] = {}
        existing_by_mpn: dict[str, LaptopConfiguration] = {}

        for i in range(0, max(len(canonical_ids), len(mpns), 1), batch_size):
            cid_chunk = canonical_ids[i : i + batch_size]
            mpn_chunk = mpns[i : i + batch_size]

            conditions = []
            if cid_chunk:
                conditions.append(LaptopConfiguration.canonical_id.in_(cid_chunk))
            if mpn_chunk:
                conditions.append(
                    and_(
                        LaptopConfiguration.mpn.is_not(None),
                        LaptopConfiguration.mpn.in_(mpn_chunk),
                    )
                )

            if not conditions:
                continue

            stmt = (
                select(LaptopConfiguration)
                .where(or_(*conditions))
                .options(
                    selectinload(LaptopConfiguration.offers),
                    selectinload(LaptopConfiguration.metrics),
                )
            )
            result = await self.session.execute(stmt)
            for laptop in result.scalars().all():
                if laptop.canonical_id:
                    existing_by_canonical[laptop.canonical_id] = laptop
                if laptop.mpn:
                    existing_by_mpn[laptop.mpn.upper()] = laptop

        # Step 3: Iterate and upsert
        for item in raw_laptops:
            total_processed += 1
            cid = item.get("canonical_id")
            if not cid:
                logger.warning("Skipping catalog item missing 'canonical_id': %s", item.get("title"))
                continue

            cid_str = str(cid).strip()
            mpn_val = item.get("mpn") or item.get("specs", {}).get("identity", {}).get("manufacturer_part_number")
            mpn_str = str(mpn_val).strip() if mpn_val else None

            # Identity match
            existing_laptop = existing_by_canonical.get(cid_str)
            if existing_laptop is None and mpn_str:
                existing_laptop = existing_by_mpn.get(mpn_str.upper())

            if existing_laptop is not None:
                target_laptop = existing_laptop
                new_min_price = _safe_float(item.get("min_price_egp"), default=0.0) or 0.0
                if (
                    target_laptop.min_price_egp is not None
                    and abs(float(target_laptop.min_price_egp) - new_min_price) > 0.01
                ):
                    target_laptop.previous_min_price_egp = target_laptop.min_price_egp
                    target_laptop.price_updated_at = now
                self._populate_laptop_fields(target_laptop, item, now)
                updated_laptops_count += 1
            else:
                target_laptop = LaptopConfiguration(id=uuid.uuid4(), canonical_id=cid_str)
                self._populate_laptop_fields(target_laptop, item, now)
                target_laptop.laptop_added_at = now
                self.session.add(target_laptop)
                existing_by_canonical[cid_str] = target_laptop
                if mpn_str:
                    existing_by_mpn[mpn_str.upper()] = target_laptop
                new_laptops_count += 1

            # Step 4: Upsert offers
            offers_data = item.get("offers", [])
            existing_offers_by_store: dict[str, LaptopOffer] = {}
            existing_offers_by_url: dict[str, LaptopOffer] = {}

            for off in target_laptop.offers:
                if off.store_key:
                    existing_offers_by_store[off.store_key.lower().strip()] = off
                if off.product_url:
                    existing_offers_by_url[off.product_url.strip()] = off

            for off_dict in offers_data:
                store_k = _safe_str(off_dict.get("store_key"), "generic", max_length=50).lower().strip()
                prod_u = _safe_str(off_dict.get("product_url"), "") or ""

                matched_offer = existing_offers_by_store.get(store_k) or (
                    existing_offers_by_url.get(prod_u) if prod_u else None
                )

                if matched_offer is not None:
                    self._populate_offer_fields(matched_offer, off_dict, target_laptop.id, now)
                    updated_offers_count += 1
                else:
                    new_offer = LaptopOffer(
                        id=uuid.uuid4(),
                        laptop_configuration_id=target_laptop.id,
                        store_key=store_k,
                        product_url=prod_u,
                        created_at=now,
                    )
                    self._populate_offer_fields(new_offer, off_dict, target_laptop.id, now)
                    target_laptop.offers.append(new_offer)
                    self.session.add(new_offer)
                    existing_offers_by_store[store_k] = new_offer
                    if prod_u:
                        existing_offers_by_url[prod_u] = new_offer
                    created_offers_count += 1

            # Step 5: Upsert metrics
            metrics_data = item.get("derived_metrics") or item.get("hardware_metrics")
            if metrics_data and isinstance(metrics_data, dict):
                if target_laptop.metrics is not None:
                    self._populate_metrics_fields(target_laptop.metrics, metrics_data, target_laptop.id, now)
                    updated_metrics_count += 1
                else:
                    new_metrics = LaptopMetrics(laptop_id=target_laptop.id)
                    self._populate_metrics_fields(new_metrics, metrics_data, target_laptop.id, now)
                    target_laptop.metrics = new_metrics
                    self.session.add(new_metrics)
                    created_metrics_count += 1

        await self.session.flush()

        summary = SeederSummary(
            total_laptops_processed=total_processed,
            new_laptops_created=new_laptops_count,
            laptops_updated=updated_laptops_count,
            offers_created=created_offers_count,
            offers_updated=updated_offers_count,
            metrics_created=created_metrics_count,
            metrics_updated=updated_metrics_count,
        )

        logger.info(
            "Seeding completed: %d processed (%d new, %d updated laptops | %d new, %d updated offers | %d new, %d updated metrics)",
            summary.total_laptops_processed,
            summary.new_laptops_created,
            summary.laptops_updated,
            summary.offers_created,
            summary.offers_updated,
            summary.metrics_created,
            summary.metrics_updated,
        )

        return summary

    def _populate_laptop_fields(
        self,
        laptop: LaptopConfiguration,
        item: dict[str, Any],
        now: datetime,
    ) -> None:
        """Populate or update all 35+ typed columns of LaptopConfiguration."""
        specs: dict[str, Any] = item.get("specs") or {}
        ident: dict[str, Any] = specs.get("identity") or {}
        cpu: dict[str, Any] = specs.get("cpu") or {}
        gpu: dict[str, Any] = specs.get("gpu") or {}
        mem: dict[str, Any] = specs.get("memory") or {}
        storage: dict[str, Any] = specs.get("storage") or {}
        disp: dict[str, Any] = specs.get("display") or {}
        pwr: dict[str, Any] = specs.get("power_battery") or {}
        phys: dict[str, Any] = specs.get("physical") or {}
        bld: dict[str, Any] = specs.get("build_security") or {}
        aud: dict[str, Any] = specs.get("audio_webcam") or {}
        conn: dict[str, Any] = specs.get("connectivity") or {}
        os_spec: dict[str, Any] = specs.get("operating_system") or {}

        # Identity & Presentation
        laptop.canonical_id = _safe_str(item.get("canonical_id"), max_length=255) or str(item.get("canonical_id"))
        laptop.mpn = _safe_str(item.get("mpn") or ident.get("manufacturer_part_number"), max_length=100)
        laptop.brand = _safe_str(ident.get("brand") or item.get("brand"), "Generic", max_length=50) or "Generic"
        laptop.laptop_family = _safe_str(ident.get("laptop_family") or item.get("laptop_family"), max_length=100)
        laptop.laptop_model = (
            _safe_str(
                ident.get("laptop_model") or item.get("laptop_model") or item.get("title"),
                "Generic Model",
                max_length=150,
            )
            or "Generic Model"
        )
        laptop.title = _safe_str(item.get("title"), laptop.laptop_model) or laptop.laptop_model
        laptop.thumbnail_url = _safe_str(item.get("thumbnail_url"))
        laptop.base_color = _safe_str(ident.get("base_color"), max_length=50)
        laptop.color = _safe_str(ident.get("color"), max_length=50)
        laptop.form_factor = _safe_str(ident.get("form_factor"), "Clamshell", max_length=50) or "Clamshell"
        laptop.market_positioning = _safe_str(ident.get("market_positioning"), max_length=50)
        laptop.release_year = _safe_int(ident.get("release_year"))
        laptop.warranty = _safe_str(ident.get("warranty"), max_length=100)
        laptop.warranty_years = _safe_int(ident.get("warranty_years"))
        laptop.is_bundle = _safe_bool(ident.get("is_bundle"), False)

        # CPU
        laptop.cpu_manufacturer = _safe_str(cpu.get("manufacturer"), "Unknown", max_length=50) or "Unknown"
        laptop.cpu_line = _safe_str(cpu.get("line"), max_length=50)
        laptop.cpu_model = _safe_str(cpu.get("model"), "Unknown", max_length=100) or "Unknown"
        laptop.cpu_series = _safe_str(cpu.get("series"), max_length=50)
        laptop.cpu_full_name = _safe_str(cpu.get("full_name"), max_length=120)
        laptop.cpu_cores = _safe_int(cpu.get("cores"), default=4) or 4
        laptop.cpu_threads = _safe_int(cpu.get("threads"), default=laptop.cpu_cores) or laptop.cpu_cores
        laptop.cpu_base_clock_ghz = _safe_float(cpu.get("clock_base_ghz"))
        laptop.cpu_boost_clock_ghz = _safe_float(cpu.get("clock_boost_ghz"))
        laptop.cpu_cache_mb = _safe_int(cpu.get("cache_mb"))
        laptop.cpu_base_power_w = _safe_int(cpu.get("base_power_w"))
        laptop.cpu_npu_tops = _safe_float(cpu.get("npu_tops"))
        laptop.cpu_microarchitecture = _safe_str(cpu.get("microarchitecture"), max_length=50)

        # GPU
        laptop.gpu_manufacturer = _safe_str(gpu.get("manufacturer"), "Unknown", max_length=50) or "Unknown"
        laptop.gpu_model = _safe_str(gpu.get("model"), "Integrated", max_length=100) or "Integrated"
        laptop.gpu_variant = _safe_str(gpu.get("variant"), max_length=50)
        laptop.gpu_vram_gb = _safe_int(gpu.get("vram_gb"))
        laptop.gpu_vram_type = _safe_str(gpu.get("vram_type"), max_length=20)
        laptop.gpu_tdp_w = _safe_int(gpu.get("tdp_w"))
        laptop.gpu_integrated = _safe_bool(gpu.get("integrated"), False)
        laptop.gpu_ai_tops = _safe_int(gpu.get("ai_tops"))
        laptop.gpu_igpu_model = _safe_str(gpu.get("igpu_model"), max_length=100)

        # Memory (RAM)
        laptop.ram_capacity_gb = _safe_int(mem.get("capacity_gb"), default=8) or 8
        laptop.ram_type = _safe_str(mem.get("memory_type"), "DDR4", max_length=20) or "DDR4"
        laptop.ram_speed_mhz = _safe_int(mem.get("speed"))
        laptop.ram_slot_count = _safe_int(mem.get("slot_count"))
        laptop.ram_max_supported_gb = _safe_int(mem.get("max_supported_gb"))
        laptop.ram_is_soldered = _safe_bool(mem.get("is_soldered"), False)
        laptop.ram_channels = _safe_str(mem.get("channels"), max_length=30)

        # Storage
        laptop.storage_capacity_gb = _safe_int(storage.get("capacity_gb"), default=256) or 256
        laptop.storage_type = _safe_str(storage.get("storage_type"), "SSD", max_length=20) or "SSD"
        laptop.storage_interface = _safe_str(storage.get("interface"), max_length=50)
        laptop.storage_slot_count = _safe_int(storage.get("slot_count"))

        # Display
        laptop.display_size_inches = _safe_float(disp.get("size_inches"), default=15.6) or 15.6
        laptop.display_resolution = _safe_str(disp.get("resolution"), "1920x1080", max_length=30) or "1920x1080"
        laptop.display_width = _safe_int(disp.get("resolution_width"), default=1920) or 1920
        laptop.display_height = _safe_int(disp.get("resolution_height"), default=1080) or 1080
        laptop.display_panel_type = _safe_str(disp.get("panel_type"), max_length=30)
        laptop.display_refresh_rate_hz = _safe_int(disp.get("refresh_rate_hz"), default=60) or 60
        laptop.display_aspect_ratio = _safe_str(disp.get("aspect_ratio"), "16:9", max_length=20) or "16:9"
        laptop.display_brightness_nits = _safe_int(disp.get("brightness_nits"))
        laptop.display_color_gamut = _safe_str(disp.get("color_gamut"), max_length=50)
        laptop.display_touchscreen = _safe_bool(disp.get("touchscreen"), False)
        laptop.display_hdr = _safe_bool(disp.get("hdr"), False)

        # Power & Battery
        laptop.battery_capacity_wh = _safe_float(pwr.get("battery_capacity_wh"))
        laptop.battery_cells = _safe_int(pwr.get("battery_cells"))
        laptop.power_adapter_w = _safe_float(pwr.get("power_adapter_w"))
        laptop.fast_charging = _safe_bool(pwr.get("fast_charging"), False)
        laptop.usb_c_pd_charging = _safe_bool(
            pwr.get("usb_c_pd_charging") or conn.get("usb_c_power_delivery"),
            False,
        )

        # Physical
        laptop.weight_kg = _safe_float(phys.get("weight_kg"))
        laptop.width_mm = _safe_float(phys.get("width_mm"))
        laptop.depth_mm = _safe_float(phys.get("depth_mm"))
        laptop.height_mm = _safe_float(phys.get("height_mm") or phys.get("height_rear_mm"))

        # Build, Audio & Webcam
        laptop.has_backlit_keyboard = _safe_bool(bld.get("has_backlit_keyboard"), False)
        laptop.keyboard_backlight_type = _safe_str(bld.get("keyboard_backlight_type"), max_length=50)
        laptop.has_fingerprint = _safe_bool(bld.get("has_fingerprint"), False)
        laptop.has_copilot_key = _safe_bool(bld.get("has_copilot_key"), False)
        laptop.security_features = _safe_list(bld.get("security_features"))
        laptop.speaker_count = _safe_int(aud.get("speaker_count"), default=2) or 2
        laptop.audio_system = _safe_str(aud.get("audio_system"), max_length=50)
        laptop.webcam_resolution = _safe_str(aud.get("webcam_resolution"), max_length=30)
        laptop.has_ir_camera = _safe_bool(aud.get("has_ir_camera"), False)
        laptop.has_privacy_shutter = _safe_bool(aud.get("has_privacy_shutter"), False)

        # Connectivity & OS
        laptop.wifi = _safe_str(conn.get("wifi"), max_length=50)
        laptop.bluetooth = _safe_str(conn.get("bluetooth"), max_length=50)
        laptop.has_ethernet = _safe_bool(conn.get("ethernet"), False)
        laptop.ethernet_speed = _safe_str(conn.get("ethernet_speed"), max_length=30)
        laptop.has_card_reader = _safe_bool(conn.get("has_card_reader"), False)
        laptop.operating_system = _safe_str(os_spec.get("name"), max_length=50)
        laptop.ports = _safe_list(conn.get("ports"))

        # Aggregated Pricing & Stock Rollups
        laptop.min_price_egp = _safe_float(item.get("min_price_egp"), default=0.0) or 0.0
        laptop.max_price_egp = _safe_float(item.get("max_price_egp"))
        laptop.cheapest_store = _safe_str(item.get("cheapest_store"), "unknown", max_length=50) or "unknown"
        laptop.price_spread_egp = _safe_float(item.get("price_spread_egp"))
        laptop.stores_count = (
            _safe_int(item.get("stores_count"), default=len(item.get("offers", []))) or len(item.get("offers", [])) or 1
        )
        if item.get("offers"):
            laptop.in_stock = any(_safe_bool(o.get("in_stock", True)) for o in item.get("offers", []))
        else:
            laptop.in_stock = _safe_bool(item.get("in_stock"), True)

        laptop.available_stores = item.get("available_stores") or [
            str(o.get("store_key")).strip() for o in item.get("offers", []) if o.get("store_key")
        ]

        # Timestamps
        laptop.price_checked_at = now
        laptop.updated_at = now

    def _populate_offer_fields(
        self,
        offer: LaptopOffer,
        item: dict[str, Any],
        laptop_id: uuid.UUID,
        now: datetime,
    ) -> None:
        """Populate or update fields of a LaptopOffer."""
        offer.laptop_configuration_id = laptop_id
        offer.store_key = _safe_str(item.get("store_key"), "generic", max_length=50).lower().strip()
        offer.store_name = _safe_str(item.get("store_name"), offer.store_key, max_length=100) or offer.store_key
        offer.store_domain = _safe_str(item.get("store_domain"), max_length=100)
        offer.product_url = _safe_str(item.get("product_url"), "") or ""
        offer.retailer_sku = _safe_str(item.get("retailer_sku"), max_length=100)
        offer.mpn = _safe_str(item.get("mpn"), max_length=100)

        new_price = _safe_float(item.get("price_egp"), default=0.0) or 0.0
        if offer.price_egp is not None and abs(float(offer.price_egp) - new_price) > 0.01:
            offer.previous_price_egp = offer.price_egp
            offer.price_egp = new_price
            offer.price_updated_at = now
        else:
            offer.price_egp = new_price

        offer.in_stock = _safe_bool(item.get("in_stock"), True)
        offer.is_valid_price = _safe_bool(item.get("is_valid_price"), True)
        offer.scraped_at = _parse_datetime(item.get("scraped_at")) or now
        offer.last_checked_at = now

    def _populate_metrics_fields(
        self,
        metrics: LaptopMetrics,
        item: dict[str, Any],
        laptop_id: uuid.UUID,
        now: datetime,
    ) -> None:
        """Populate or update all normalized 1:1 hardware performance scores and TOPSIS inputs."""
        metrics.laptop_id = laptop_id
        topsis: dict[str, Any] = item.get("topsis_inputs") or {}
        silicon: dict[str, Any] = item.get("silicon") or {}
        power: dict[str, Any] = item.get("power") or {}
        disp: dict[str, Any] = item.get("display") or {}
        mob: dict[str, Any] = item.get("mobility") or {}
        longv: dict[str, Any] = item.get("longevity") or {}
        econ: dict[str, Any] = item.get("economics") or {}

        # 11 Flat TOPSIS Float Scores (0.00 to 100.00)
        metrics.cpu_score = (
            _safe_float(topsis.get("cpu_score") or silicon.get("effective_cpu_score"), default=0.0) or 0.0
        )
        metrics.gpu_score = (
            _safe_float(topsis.get("gpu_score") or silicon.get("effective_gpu_score"), default=0.0) or 0.0
        )
        metrics.silicon_index = (
            _safe_float(topsis.get("silicon_index") or silicon.get("silicon_index"), default=0.0) or 0.0
        )
        metrics.power_therm_score = (
            _safe_float(topsis.get("power_therm_score") or power.get("power_score"), default=0.0) or 0.0
        )
        metrics.display_score = (
            _safe_float(topsis.get("display_score") or disp.get("display_score"), default=0.0) or 0.0
        )
        metrics.mobility_score = (
            _safe_float(topsis.get("mobility_score") or mob.get("portability_score"), default=0.0) or 0.0
        )
        metrics.longevity_score = (
            _safe_float(topsis.get("longevity_score") or longv.get("upgradeability_score"), default=0.0) or 0.0
        )
        metrics.ergonomics_score = _safe_float(topsis.get("ergonomics_score"), default=0.0) or 0.0
        metrics.connectivity_score = _safe_float(topsis.get("connectivity_score"), default=0.0) or 0.0
        metrics.community_nlp_score = _safe_float(topsis.get("community_nlp_score"), default=50.0) or 50.0
        metrics.value_score = _safe_float(topsis.get("value_score") or econ.get("value_score"), default=0.0) or 0.0

        # Operational Meta
        metrics.effective_price_egp = (
            _safe_float(topsis.get("effective_price_egp") or econ.get("min_price_egp"), default=0.0) or 0.0
        )
        metrics.is_recommendable_price = _safe_bool(topsis.get("is_recommendable_price"), True)
        metrics.in_stock_active = _safe_bool(topsis.get("in_stock_active"), True)

        # Computed Sub-Metrics & Tiers
        metrics.delta_p_watts = _safe_float(power.get("delta_p_watts"), default=0.0) or 0.0
        metrics.simultaneous_load_w = _safe_float(power.get("simultaneous_load_w"), default=0.0) or 0.0
        metrics.electrical_status = _safe_str(power.get("electrical_status"), "UNKNOWN", max_length=30) or "UNKNOWN"
        metrics.estimated_battery_hours = _safe_float(mob.get("battery_hours_estimate"), default=0.0) or 0.0
        metrics.silicon_tier = _safe_str(silicon.get("tgp_source"), "STANDARD", max_length=50) or "STANDARD"
        metrics.display_tier = _safe_str(disp.get("color_gamut_tier"), "STANDARD", max_length=50) or "STANDARD"
        metrics.portability_tier = _safe_str(mob.get("portability_tier"), "BALANCED", max_length=30) or "BALANCED"
        metrics.upgradeability_tier = (
            _safe_str(longv.get("upgradeability_tier"), "MODERATE", max_length=50) or "MODERATE"
        )
        metrics.is_copilot_plus_pc = _safe_bool(silicon.get("is_copilot_plus_pc"), False)
        metrics.pricing_status = (
            _safe_str(econ.get("pricing_status"), "IN_STOCK_ACTIVE", max_length=30) or "IN_STOCK_ACTIVE"
        )

        metrics.updated_at = now
