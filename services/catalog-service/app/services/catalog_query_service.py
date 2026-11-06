"""Catalog Query Application Service.

Coordinates retrieval of full canonical laptop configurations, specifications,
store offers, and hardware scores for front-end product details and user experience.
Adheres strictly to Clean Architecture and SOLID principles.
"""

import json
from pathlib import Path
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.logger import get_logger
from app.domain.recommender.explainer import build_why_recommended
from app.models.laptop import LaptopConfiguration
from app.repositories.laptop_repository import LaptopRepository, to_recommender_dict
from app.schemas.laptop import (
    AudioWebcamSpecDetail,
    BuildSecuritySpecDetail,
    ConnectivityOsSpecDetail,
    CpuSpecDetail,
    DetailedOfferRead,
    DisplaySpecDetail,
    FullLaptopDetailResponse,
    GpuSpecDetail,
    HardwareMetricsDetail,
    MemorySpecDetail,
    PhysicalSpecDetail,
    PowerBatterySpecDetail,
    StorageSpecDetail,
)

logger = get_logger("catalog.services.catalog_query")

FALLBACK_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "scraping input" / "unified_catalog_latest.json"
)


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


class CatalogQueryService:
    """Application use-case service for catalog detail queries."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        laptop_repo: LaptopRepository | None = None,
    ):
        self.session = session
        self.laptop_repo = laptop_repo or (LaptopRepository(session) if session is not None else None)
        self._fallback_catalog: list[dict[str, Any]] | None = None

    def _load_fallback_catalog(self) -> list[dict[str, Any]]:
        """Load local fallback catalog when database is unreachable or missing a record."""
        if self._fallback_catalog is None:
            if FALLBACK_CATALOG_PATH.exists():
                try:
                    with open(FALLBACK_CATALOG_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._fallback_catalog = data.get("laptops", [])
                    logger.info("Loaded %d laptops into query fallback cache.", len(self._fallback_catalog))
                except Exception as exc:
                    logger.warning("Could not load fallback catalog JSON: %s", exc)
                    self._fallback_catalog = []
            else:
                self._fallback_catalog = []
        return self._fallback_catalog

    async def get_laptop_detail(self, identifier: str) -> FullLaptopDetailResponse:
        """Fetch complete laptop specifications, offers, and metrics by UUID, canonical_id, or MPN."""
        clean_id = identifier.strip()
        if not clean_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Laptop identifier cannot be empty.",
            )

        # 1. Primary path: query repository / database
        if self.laptop_repo is not None:
            try:
                laptop = await self.laptop_repo.get_by_identifier(clean_id)
                if laptop is not None:
                    return self._orm_to_full_detail(laptop)
            except Exception as exc:
                logger.warning(
                    "Database query for laptop identifier '%s' failed (%s); checking fallback catalog.",
                    clean_id,
                    exc,
                )

        # 2. Fallback path: JSON file lookup
        fallback_laptops = self._load_fallback_catalog()
        lower_id = clean_id.lower()
        for lap in fallback_laptops:
            c_id = str(lap.get("canonical_id") or "").lower()
            m_id = str(lap.get("mpn") or "").lower()
            u_id = str(lap.get("id") or "").lower()
            if lower_id in (c_id, m_id, u_id):
                return self._dict_to_full_detail(lap)

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Laptop '{clean_id}' was not found in the catalog.",
        )

    def _orm_to_full_detail(self, laptop: LaptopConfiguration) -> FullLaptopDetailResponse:
        """Convert a LaptopConfiguration ORM instance to FullLaptopDetailResponse."""
        cheapest_store_key = str(laptop.cheapest_store or "unknown").lower().strip()
        prices_by_store: dict[str, float] = {}
        urls_by_store: dict[str, str] = {}
        available_stores: list[str] = []
        formatted_offers: list[DetailedOfferRead] = []
        cheapest_offer_url: str | None = None

        if laptop.offers:
            for off in laptop.offers:
                store_k = (off.store_key or "generic").lower().strip()
                price_val = float(off.price_egp) if off.price_egp is not None else 0.0
                p_url = off.product_url or ""
                in_stk = bool(off.in_stock)
                is_valid = bool(off.is_valid_price) if off.is_valid_price is not None else True
                is_chp = (store_k == cheapest_store_key)

                if store_k not in available_stores:
                    available_stores.append(store_k)
                if is_valid and price_val > 0:
                    prices_by_store[store_k] = price_val
                if p_url:
                    urls_by_store[store_k] = p_url

                if is_chp and p_url and not cheapest_offer_url:
                    cheapest_offer_url = p_url

                formatted_offers.append(
                    DetailedOfferRead(
                        id=str(off.id) if off.id else None,
                        store_key=store_k,
                        store_name=off.store_name or store_k.capitalize(),
                        store_domain=off.store_domain,
                        product_url=p_url,
                        retailer_sku=off.retailer_sku,
                        mpn=off.mpn,
                        price_egp=price_val,
                        previous_price_egp=float(off.previous_price_egp) if off.previous_price_egp else None,
                        in_stock=in_stk,
                        is_valid_price=is_valid,
                        is_cheapest=is_chp,
                        price_updated_at=off.price_updated_at,
                        last_checked_at=off.last_checked_at,
                    )
                )

        if not cheapest_offer_url and urls_by_store:
            cheapest_offer_url = urls_by_store.get(cheapest_store_key) or next(iter(urls_by_store.values()), None)

        if not available_stores and laptop.available_stores:
            available_stores = list(laptop.available_stores)

        # Hardware metrics mapping
        metrics_detail: HardwareMetricsDetail | None = None
        if laptop.metrics:
            m = laptop.metrics
            metrics_detail = HardwareMetricsDetail(
                cpu_score=float(m.cpu_score) if m.cpu_score is not None else 50.0,
                gpu_score=float(m.gpu_score) if m.gpu_score is not None else 50.0,
                silicon_index=float(m.silicon_index) if m.silicon_index is not None else None,
                power_therm_score=float(m.power_therm_score) if m.power_therm_score is not None else 50.0,
                display_score=float(m.display_score) if m.display_score is not None else 50.0,
                mobility_score=float(m.mobility_score) if m.mobility_score is not None else 50.0,
                longevity_score=float(m.longevity_score) if m.longevity_score is not None else 50.0,
                ergonomics_score=float(m.ergonomics_score) if m.ergonomics_score is not None else 50.0,
                connectivity_score=float(m.connectivity_score) if m.connectivity_score is not None else 50.0,
                community_nlp_score=float(m.community_nlp_score) if m.community_nlp_score is not None else None,
                value_score=float(m.value_score) if m.value_score is not None else 50.0,
                effective_price_egp=(
                    float(m.effective_price_egp)
                    if m.effective_price_egp is not None
                    else float(laptop.min_price_egp or 0.0)
                ),
                estimated_battery_hours=float(m.estimated_battery_hours) if m.estimated_battery_hours is not None else None,
                silicon_tier=m.silicon_tier,
                display_tier=m.display_tier,
                portability_tier=m.portability_tier,
                upgradeability_tier=m.upgradeability_tier,
            )

        # Explainable reasons
        lap_dict = to_recommender_dict(laptop)
        reasons = build_why_recommended(lap_dict, "balanced")

        return FullLaptopDetailResponse(
            id=str(laptop.id),
            canonical_id=laptop.canonical_id,
            mpn=laptop.mpn,
            brand=laptop.brand,
            laptop_family=laptop.laptop_family,
            laptop_model=laptop.laptop_model,
            title=laptop.title,
            thumbnail_url=laptop.thumbnail_url,
            base_color=laptop.base_color,
            color=laptop.color,
            form_factor=laptop.form_factor or "Clamshell",
            market_positioning=laptop.market_positioning,
            release_year=laptop.release_year,
            warranty=laptop.warranty,
            warranty_years=laptop.warranty_years,
            min_price_egp=float(laptop.min_price_egp),
            max_price_egp=float(laptop.max_price_egp) if laptop.max_price_egp else float(laptop.min_price_egp),
            previous_min_price_egp=float(laptop.previous_min_price_egp) if laptop.previous_min_price_egp else None,
            cheapest_store=laptop.cheapest_store or "unknown",
            cheapest_offer_url=cheapest_offer_url,
            price_spread_egp=float(laptop.price_spread_egp) if laptop.price_spread_egp else 0.0,
            stores_count=laptop.stores_count or len(formatted_offers) or 1,
            in_stock=bool(laptop.in_stock),
            price_updated_at=laptop.price_updated_at,
            price_checked_at=laptop.price_checked_at,
            available_stores=available_stores,
            prices_by_store=prices_by_store,
            urls_by_store=urls_by_store,
            offers=formatted_offers,
            cpu=CpuSpecDetail(
                manufacturer=laptop.cpu_manufacturer,
                line=laptop.cpu_line,
                model=laptop.cpu_model,
                series=laptop.cpu_series,
                full_name=laptop.cpu_full_name or f"{laptop.cpu_manufacturer} {laptop.cpu_model}".strip(),
                cores=laptop.cpu_cores or 0,
                threads=laptop.cpu_threads or 0,
                clock_base_ghz=float(laptop.cpu_base_clock_ghz) if laptop.cpu_base_clock_ghz else None,
                clock_boost_ghz=float(laptop.cpu_boost_clock_ghz) if laptop.cpu_boost_clock_ghz else None,
                cache_mb=laptop.cpu_cache_mb,
                base_power_w=laptop.cpu_base_power_w,
                npu_tops=float(laptop.cpu_npu_tops) if laptop.cpu_npu_tops else None,
                microarchitecture=laptop.cpu_microarchitecture,
            ),
            gpu=GpuSpecDetail(
                manufacturer=laptop.gpu_manufacturer,
                model=laptop.gpu_model,
                variant=laptop.gpu_variant,
                vram_gb=laptop.gpu_vram_gb,
                vram_type=laptop.gpu_vram_type,
                tdp_w=laptop.gpu_tdp_w,
                integrated=bool(laptop.gpu_integrated),
                ai_tops=laptop.gpu_ai_tops,
                igpu_model=laptop.gpu_igpu_model,
            ),
            memory=MemorySpecDetail(
                capacity_gb=laptop.ram_capacity_gb or 0,
                memory_type=laptop.ram_type or "DDR4",
                speed_mhz=laptop.ram_speed_mhz,
                slot_count=laptop.ram_slot_count,
                max_supported_gb=laptop.ram_max_supported_gb,
                is_soldered=bool(laptop.ram_is_soldered),
                channels=laptop.ram_channels,
            ),
            storage=StorageSpecDetail(
                capacity_gb=laptop.storage_capacity_gb or 0,
                storage_type=laptop.storage_type or "SSD",
                interface=laptop.storage_interface,
                slot_count=laptop.storage_slot_count,
            ),
            display=DisplaySpecDetail(
                size_inches=float(laptop.display_size_inches) if laptop.display_size_inches else 15.6,
                resolution=laptop.display_resolution or "1920x1080",
                width=laptop.display_width or 1920,
                height=laptop.display_height or 1080,
                panel_type=laptop.display_panel_type,
                refresh_rate_hz=laptop.display_refresh_rate_hz or 60,
                aspect_ratio=laptop.display_aspect_ratio or "16:9",
                brightness_nits=laptop.display_brightness_nits,
                color_gamut=laptop.display_color_gamut,
                touchscreen=bool(laptop.display_touchscreen),
                hdr=bool(laptop.display_hdr),
            ),
            power_battery=PowerBatterySpecDetail(
                battery_capacity_wh=float(laptop.battery_capacity_wh) if laptop.battery_capacity_wh else None,
                battery_cells=laptop.battery_cells,
                power_adapter_w=float(laptop.power_adapter_w) if laptop.power_adapter_w else None,
                fast_charging=bool(laptop.fast_charging),
                usb_c_pd_charging=bool(laptop.usb_c_pd_charging),
            ),
            physical=PhysicalSpecDetail(
                weight_kg=float(laptop.weight_kg) if laptop.weight_kg else None,
                width_mm=float(laptop.width_mm) if laptop.width_mm else None,
                depth_mm=float(laptop.depth_mm) if laptop.depth_mm else None,
                height_mm=float(laptop.height_mm) if laptop.height_mm else None,
            ),
            build_security=BuildSecuritySpecDetail(
                has_backlit_keyboard=bool(laptop.has_backlit_keyboard),
                keyboard_backlight_type=laptop.keyboard_backlight_type,
                has_fingerprint=bool(laptop.has_fingerprint),
                has_copilot_key=bool(laptop.has_copilot_key),
                security_features=list(laptop.security_features or []),
            ),
            audio_webcam=AudioWebcamSpecDetail(
                speaker_count=laptop.speaker_count or 2,
                audio_system=laptop.audio_system,
                webcam_resolution=laptop.webcam_resolution,
                has_ir_camera=bool(laptop.has_ir_camera),
                has_privacy_shutter=bool(laptop.has_privacy_shutter),
            ),
            connectivity_os=ConnectivityOsSpecDetail(
                wifi=laptop.wifi,
                bluetooth=laptop.bluetooth,
                has_ethernet=bool(laptop.has_ethernet),
                ethernet_speed=laptop.ethernet_speed,
                has_card_reader=bool(laptop.has_card_reader),
                operating_system=laptop.operating_system,
                ports=list(laptop.ports or []),
            ),
            metrics=metrics_detail,
            why_recommended_ar=reasons.get("ar", []),
            why_recommended_en=reasons.get("en", []),
        )

    def _dict_to_full_detail(self, lap: dict[str, Any]) -> FullLaptopDetailResponse:
        """Convert a raw dictionary (from unified_catalog_latest.json) to FullLaptopDetailResponse."""
        specs = lap.get("specs") or {}
        cpu = specs.get("cpu") or {}
        gpu = specs.get("gpu") or {}
        mem = specs.get("memory") or {}
        sto = specs.get("storage") or {}
        dsp = specs.get("display") or {}
        pwr = specs.get("power_battery") or {}
        phy = specs.get("physical") or {}
        sec = specs.get("build_security") or {}
        aud = specs.get("audio_webcam") or {}
        con = specs.get("connectivity") or {}
        os_spec = specs.get("operating_system") or {}

        dm = lap.get("derived_metrics") or {}
        topsis = dm.get("topsis_inputs") or {}
        sil_dm = dm.get("silicon") or {}
        dsp_dm = dm.get("display") or {}
        mob_dm = dm.get("mobility") or {}
        lon_dm = dm.get("longevity") or {}

        cheapest_store_key = str(lap.get("cheapest_store") or "unknown").lower().strip()
        prices_by_store = dict(lap.get("prices_by_store") or {})
        urls_by_store = dict(lap.get("urls_by_store") or {})
        raw_offers = list(lap.get("offers") or [])
        formatted_offers: list[DetailedOfferRead] = []
        cheapest_offer_url: str | None = lap.get("cheapest_offer_url")
        available_stores: list[str] = list(lap.get("available_stores") or [])

        for off in raw_offers:
            store_k = str(off.get("store_key") or "generic").lower().strip()
            price_val = float(off.get("price_egp") or 0.0)
            p_url = off.get("product_url") or ""
            is_chp = (store_k == cheapest_store_key)

            if store_k not in available_stores:
                available_stores.append(store_k)
            if price_val > 0 and off.get("is_valid_price", True):
                prices_by_store[store_k] = price_val
            if p_url:
                urls_by_store[store_k] = p_url

            if is_chp and p_url and not cheapest_offer_url:
                cheapest_offer_url = p_url

            formatted_offers.append(
                DetailedOfferRead(
                    store_key=store_k,
                    store_name=off.get("store_name") or store_k.capitalize(),
                    store_domain=off.get("store_domain"),
                    product_url=p_url,
                    retailer_sku=off.get("retailer_sku"),
                    mpn=off.get("mpn"),
                    price_egp=price_val,
                    previous_price_egp=float(off.get("previous_price_egp")) if off.get("previous_price_egp") else None,
                    in_stock=bool(off.get("in_stock", True)),
                    is_valid_price=bool(off.get("is_valid_price", True)),
                    is_cheapest=is_chp,
                    price_updated_at=off.get("price_updated_at") or off.get("scraped_at"),
                    last_checked_at=off.get("last_checked_at") or off.get("last_checked") or off.get("price_updated_at") or off.get("scraped_at"),
                )
            )

        if not cheapest_offer_url and urls_by_store:
            cheapest_offer_url = urls_by_store.get(cheapest_store_key) or next(iter(urls_by_store.values()), None)

        min_price = float(lap.get("min_price_egp") or 0.0)
        max_price = float(lap.get("max_price_egp") or min_price)

        metrics_detail: HardwareMetricsDetail | None = None
        if topsis:
            metrics_detail = HardwareMetricsDetail(
                cpu_score=float(topsis.get("cpu_score", 50.0)),
                gpu_score=float(topsis.get("gpu_score", 50.0)),
                silicon_index=float(topsis.get("silicon_index", 50.0)) if topsis.get("silicon_index") else None,
                power_therm_score=float(topsis.get("power_therm_score", 50.0)),
                display_score=float(topsis.get("display_score", 50.0)),
                mobility_score=float(topsis.get("mobility_score", 50.0)),
                longevity_score=float(topsis.get("longevity_score", 50.0)),
                ergonomics_score=float(topsis.get("ergonomics_score", 50.0)),
                connectivity_score=float(topsis.get("connectivity_score", 50.0)),
                community_nlp_score=float(topsis.get("community_nlp_score", 50.0)) if topsis.get("community_nlp_score") else None,
                value_score=float(topsis.get("value_score", 50.0)),
                effective_price_egp=float(topsis.get("effective_price_egp", min_price)),
                estimated_battery_hours=float(mob_dm.get("battery_hours_estimate")) if mob_dm.get("battery_hours_estimate") else None,
                silicon_tier=sil_dm.get("silicon_tier"),
                display_tier=dsp_dm.get("display_tier"),
                portability_tier=mob_dm.get("portability_tier"),
                upgradeability_tier=lon_dm.get("upgradeability_tier"),
            )

        reasons = build_why_recommended(lap, "balanced")

        return FullLaptopDetailResponse(
            id=str(lap.get("canonical_id") or "unknown"),
            canonical_id=str(lap.get("canonical_id") or "unknown"),
            mpn=lap.get("mpn"),
            brand=str(lap.get("brand") or "Generic"),
            laptop_family=lap.get("laptop_family"),
            laptop_model=str(lap.get("laptop_model") or "Laptop"),
            title=str(lap.get("title") or "Laptop"),
            thumbnail_url=lap.get("thumbnail_url"),
            base_color=lap.get("base_color"),
            color=lap.get("color"),
            form_factor=lap.get("form_factor") or "Clamshell",
            market_positioning=lap.get("market_positioning"),
            release_year=lap.get("release_year"),
            warranty=lap.get("warranty"),
            warranty_years=lap.get("warranty_years"),
            min_price_egp=min_price,
            max_price_egp=max_price,
            previous_min_price_egp=float(lap.get("previous_min_price_egp")) if lap.get("previous_min_price_egp") else None,
            cheapest_store=cheapest_store_key,
            cheapest_offer_url=cheapest_offer_url,
            price_spread_egp=float(lap.get("price_spread_egp") or 0.0),
            stores_count=int(lap.get("stores_count") or len(formatted_offers) or 1),
            in_stock=bool(lap.get("in_stock", True)),
            price_updated_at=lap.get("price_updated_at"),
            price_checked_at=lap.get("price_checked_at") or lap.get("price_updated_at"),
            available_stores=available_stores,
            prices_by_store=prices_by_store,
            urls_by_store=urls_by_store,
            offers=formatted_offers,
            cpu=CpuSpecDetail(
                manufacturer=str(cpu.get("manufacturer") or "Unknown"),
                line=cpu.get("line"),
                model=str(cpu.get("model") or "CPU"),
                series=cpu.get("series"),
                full_name=cpu.get("full_name") or f"{cpu.get('manufacturer', '')} {cpu.get('model', '')}".strip(),
                cores=_safe_int(cpu.get("cores"), 0) or 0,
                threads=_safe_int(cpu.get("threads"), 0) or 0,
                clock_base_ghz=_safe_float(cpu.get("clock_base_ghz")),
                clock_boost_ghz=_safe_float(cpu.get("clock_boost_ghz")),
                cache_mb=_safe_int(cpu.get("cache_mb")),
                base_power_w=_safe_int(cpu.get("base_power_w")),
                npu_tops=_safe_float(cpu.get("npu_tops")),
                microarchitecture=cpu.get("microarchitecture"),
            ),
            gpu=GpuSpecDetail(
                manufacturer=str(gpu.get("manufacturer") or "Unknown"),
                model=str(gpu.get("model") or "Integrated Graphics"),
                variant=gpu.get("variant"),
                vram_gb=_safe_int(gpu.get("vram_gb")),
                vram_type=gpu.get("vram_type"),
                tdp_w=_safe_int(gpu.get("tdp_w")),
                integrated=bool(gpu.get("integrated", True)),
                ai_tops=_safe_int(gpu.get("ai_tops")),
                igpu_model=gpu.get("igpu_model"),
            ),
            memory=MemorySpecDetail(
                capacity_gb=_safe_int(mem.get("capacity_gb"), 0) or 0,
                memory_type=str(mem.get("memory_type") or "DDR4"),
                speed_mhz=_safe_int(mem.get("speed")),
                slot_count=_safe_int(mem.get("slot_count")),
                max_supported_gb=_safe_int(mem.get("max_supported_gb")),
                is_soldered=bool(mem.get("is_soldered", False)),
                channels=mem.get("channels"),
            ),
            storage=StorageSpecDetail(
                capacity_gb=_safe_int(sto.get("capacity_gb"), 0) or 0,
                storage_type=str(sto.get("storage_type") or "SSD"),
                interface=sto.get("interface"),
                slot_count=_safe_int(sto.get("slot_count")),
            ),
            display=DisplaySpecDetail(
                size_inches=_safe_float(dsp.get("size_inches"), 15.6) or 15.6,
                resolution=str(dsp.get("resolution") or "1920x1080"),
                width=_safe_int(dsp.get("resolution_width"), 1920) or 1920,
                height=_safe_int(dsp.get("resolution_height"), 1080) or 1080,
                panel_type=dsp.get("panel_type"),
                refresh_rate_hz=_safe_int(dsp.get("refresh_rate_hz"), 60) or 60,
                aspect_ratio=dsp.get("aspect_ratio") or "16:9",
                brightness_nits=_safe_int(dsp.get("brightness_nits")),
                color_gamut=dsp.get("color_gamut"),
                touchscreen=bool(dsp.get("touchscreen", False)),
                hdr=bool(dsp.get("hdr", False)),
            ),
            power_battery=PowerBatterySpecDetail(
                battery_capacity_wh=_safe_float(pwr.get("battery_capacity_wh")),
                battery_cells=_safe_int(pwr.get("battery_cells")),
                power_adapter_w=_safe_float(pwr.get("power_adapter_w")),
                fast_charging=bool(pwr.get("fast_charging", False)),
                usb_c_pd_charging=bool(pwr.get("usb_c_pd_charging", False)),
            ),
            physical=PhysicalSpecDetail(
                weight_kg=_safe_float(phy.get("weight_kg")),
                width_mm=_safe_float(phy.get("width_mm")),
                depth_mm=_safe_float(phy.get("depth_mm")),
                height_mm=_safe_float(phy.get("height_mm")),
            ),
            build_security=BuildSecuritySpecDetail(
                has_backlit_keyboard=bool(sec.get("has_backlit_keyboard", False)),
                keyboard_backlight_type=sec.get("keyboard_backlight_type"),
                has_fingerprint=bool(sec.get("has_fingerprint", False)),
                has_copilot_key=bool(sec.get("has_copilot_key", False)),
                security_features=list(sec.get("security_features") or []),
            ),
            audio_webcam=AudioWebcamSpecDetail(
                speaker_count=_safe_int(aud.get("speaker_count"), 2) or 2,
                audio_system=aud.get("audio_system"),
                webcam_resolution=aud.get("webcam_resolution"),
                has_ir_camera=bool(aud.get("has_ir_camera", False)),
                has_privacy_shutter=bool(aud.get("has_privacy_shutter", False)),
            ),
            connectivity_os=ConnectivityOsSpecDetail(
                wifi=con.get("wifi"),
                bluetooth=con.get("bluetooth"),
                has_ethernet=bool(con.get("ethernet", False)),
                ethernet_speed=con.get("ethernet_speed"),
                has_card_reader=bool(con.get("has_card_reader", False)),
                operating_system=os_spec.get("name"),
                ports=list(con.get("ports") or []),
            ),
            metrics=metrics_detail,
            why_recommended_ar=reasons.get("ar", []),
            why_recommended_en=reasons.get("en", []),
        )
