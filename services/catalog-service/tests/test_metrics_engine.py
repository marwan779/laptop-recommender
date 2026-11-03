"""Unit tests for the Production 8-Metric Hardware Engine and Enrichment Service."""

from typing import Any
import pytest

from app.services.catalog_metrics_service import CatalogMetricsService
from app.services.metrics_engine import (
    CPU_BENCHMARK_MAP,
    GPU_BENCHMARK_MAP,
    compute_laptop_metrics,
    _clamp,
)


@pytest.fixture
def sample_gaming_laptop() -> dict[str, Any]:
    """Sample gaming laptop specification with discrete RTX 4060."""
    return {
        "canonical_id": "test_gaming_laptop_001",
        "title": "ASUS TUF Gaming A16 (FA608) - AMD Ryzen 9 8940HX - RTX 4060 - 16GB DDR5 5200 - 512GB NVMe - 16-inch 165Hz",
        "laptop_family": "Tuf Gaming",
        "min_price_egp": 45000.0,
        "max_price_egp": 48000.0,
        "cheapest_store": "compumarts",
        "price_spread_egp": 3000.0,
        "offers": [
            {
                "store_name": "Compumarts",
                "price_egp": 45000.0,
                "in_stock": True,
                "is_valid_price": True,
            }
        ],
        "specs": {
            "identity": {
                "brand": "ASUS",
                "laptop_family": "Tuf Gaming",
                "laptop_model": "FA608",
                "release_year": 2025,
            },
            "cpu": {
                "manufacturer": "AMD",
                "line": "Ryzen 9",
                "model": "Ryzen 9 8940HX",
                "cores": 16,
                "threads": 32,
                "clock_boost_ghz": 5.2,
                "cache_mb": 64,
                "base_power_w": 55,
                "npu_tops": 16.0,
            },
            "gpu": {
                "manufacturer": "NVIDIA",
                "model": "GeForce RTX 4060",
                "integrated": False,
                "tdp_w": 115.0,
                "vram_gb": 8,
                "vram_type": "GDDR6",
            },
            "memory": {
                "capacity_gb": 16,
                "memory_type": "DDR5",
                "speed": "5200 MHz",
                "slot_count": 2,
                "max_supported_gb": 64,
                "is_soldered": False,
                "layout": "2 x 8 GB",
            },
            "storage": {
                "capacity_gb": 512,
                "storage_type": "SSD",
                "interface": "PCIe 4.0 NVMe",
                "slot_count": 2,
                "installed_ssd_count": 1,
            },
            "display": {
                "size_inches": 16.0,
                "resolution_width": 1920,
                "resolution_height": 1200,
                "refresh_rate_hz": 165,
                "panel_type": "IPS",
                "color_gamut": "100% sRGB",
                "brightness_nits": 300,
                "aspect_ratio": "16:10",
                "adaptive_sync": True,
                "touchscreen": False,
            },
            "power_battery": {
                "power_adapter_w": 240.0,
                "battery_capacity_wh": 90.0,
                "fast_charging": True,
            },
            "physical": {
                "weight_kg": 2.2,
                "height_mm": 22.0,
            },
            "build_security": {
                "has_backlit_keyboard": True,
                "keyboard_backlight_type": "RGB",
                "has_numpad": True,
                "has_copilot_key": True,
                "has_fingerprint": False,
                "chassis_material": "Aluminum / PC-ABS",
            },
            "audio_webcam": {
                "webcam_resolution": "1080p",
                "has_privacy_shutter": True,
                "has_ir_camera": False,
                "speaker_count": 2,
                "audio_system": "Dolby Atmos",
            },
            "connectivity": {
                "wifi": "Wi-Fi 6E",
                "wifi_antenna": "2x2",
                "ethernet": True,
                "ethernet_speed": "1 Gbps",
                "thunderbolt_version": "USB4",
                "usb_c_displayport": True,
                "usb_c_power_delivery": True,
                "ports": ["1 x HDMI 2.1", "2 x USB 3.2 Gen 1", "2 x Type-C USB4", "1 x RJ-45"],
            },
        },
    }


@pytest.fixture
def sample_office_laptop() -> dict[str, Any]:
    """Sample ultraportable office laptop with integrated Arc GPU."""
    return {
        "canonical_id": "test_office_laptop_002",
        "title": "ASUS Zenbook 14 OLED - Intel Core Ultra 7 258V - 32GB LPDDR5X - 1TB SSD - 14-inch 120Hz OLED",
        "laptop_family": "Zenbook",
        "min_price_egp": 54000.0,
        "max_price_egp": 56000.0,
        "cheapest_store": "compumarts",
        "price_spread_egp": 2000.0,
        "offers": [
            {
                "store_name": "Compumarts",
                "price_egp": 54000.0,
                "in_stock": True,
                "is_valid_price": True,
            }
        ],
        "specs": {
            "identity": {
                "brand": "ASUS",
                "laptop_family": "Zenbook",
                "laptop_model": "UX3405",
                "release_year": 2025,
            },
            "cpu": {
                "manufacturer": "Intel",
                "line": "Core Ultra 7",
                "model": "Core Ultra 7 258V",
                "cores": 8,
                "threads": 8,
                "clock_boost_ghz": 4.8,
                "cache_mb": 12,
                "base_power_w": 17,
                "npu_tops": 47.0,
            },
            "gpu": {
                "manufacturer": "Intel",
                "model": "Intel Arc 140V",
                "integrated": True,
                "tdp_w": 0.0,
            },
            "memory": {
                "capacity_gb": 32,
                "memory_type": "LPDDR5X",
                "speed": "8533 MHz",
                "slot_count": 0,
                "max_supported_gb": 32,
                "is_soldered": True,
            },
            "storage": {
                "capacity_gb": 1024,
                "storage_type": "SSD",
                "interface": "PCIe 4.0 NVMe",
                "slot_count": 1,
                "installed_ssd_count": 1,
            },
            "display": {
                "size_inches": 14.0,
                "resolution_width": 2880,
                "resolution_height": 1800,
                "refresh_rate_hz": 120,
                "panel_type": "OLED",
                "color_gamut": "100% DCI-P3",
                "brightness_nits": 500,
                "aspect_ratio": "16:10",
                "adaptive_sync": False,
                "touchscreen": False,
            },
            "power_battery": {
                "power_adapter_w": 65.0,
                "battery_capacity_wh": 75.0,
                "fast_charging": True,
                "usb_c_pd_charging": True,
            },
            "physical": {
                "weight_kg": 1.2,
                "height_mm": 14.9,
            },
            "build_security": {
                "has_backlit_keyboard": True,
                "has_numpad": False,
                "has_copilot_key": True,
                "has_fingerprint": False,
                "chassis_material": "All-metal Aluminum",
            },
            "audio_webcam": {
                "webcam_resolution": "1080p FHD",
                "has_privacy_shutter": True,
                "has_ir_camera": True,
                "speaker_count": 4,
                "audio_system": "Harman Kardon",
            },
            "connectivity": {
                "wifi": "Wi-Fi 7",
                "wifi_antenna": "2x2",
                "ethernet": False,
                "thunderbolt_version": "Thunderbolt 4",
                "usb_c_displayport": True,
                "usb_c_power_delivery": True,
                "ports": ["2 x Thunderbolt 4", "1 x USB 3.2 Gen 1", "1 x HDMI 2.1"],
            },
        },
    }


def test_clamp_function() -> None:
    assert _clamp(50.0, 0.0, 100.0) == 50.0
    assert _clamp(-10.0, 0.0, 100.0) == 0.0
    assert _clamp(150.0, 0.0, 100.0) == 100.0


def test_topsis_inputs_structure_and_completeness(sample_gaming_laptop: dict[str, Any]) -> None:
    metrics = compute_laptop_metrics(sample_gaming_laptop)
    topsis = metrics.get("topsis_inputs")
    assert topsis is not None

    required_keys = [
        "cpu_score",
        "gpu_score",
        "silicon_index",
        "power_therm_score",
        "display_score",
        "mobility_score",
        "longevity_score",
        "ergonomics_score",
        "connectivity_score",
        "community_nlp_score",
        "value_score",
        "effective_price_egp",
        "is_recommendable_price",
        "in_stock_active",
    ]
    for k in required_keys:
        assert k in topsis, f"Missing topsis input key: {k}"
        val = topsis[k]
        if isinstance(val, (int, float)):
            assert 0.0 <= val <= 100.0 or k == "effective_price_egp"


def test_gaming_laptop_metrics(sample_gaming_laptop: dict[str, Any]) -> None:
    metrics = compute_laptop_metrics(sample_gaming_laptop)

    # 1. Silicon Performance
    silicon = metrics["silicon"]
    assert silicon["effective_cpu_score"] >= 90.0
    assert silicon["effective_gpu_score"] >= 55.0
    assert silicon["is_dual_channel"] is True

    # 2. Power Headroom
    power = metrics["power"]
    assert power["electrical_status"] == "UNCONSTRAINED_HEADROOM"
    assert power["delta_p_watts"] > 0

    # 3. Display
    display = metrics["display"]
    assert display["refresh_rate_hz"] == 165
    assert display["has_adaptive_sync"] is True

    # 4. Longevity
    longevity = metrics["longevity"]
    assert longevity["upgradeability_tier"] == "MAXIMUM_UPGRADEABLE"
    assert longevity["ram_upgradeable"] is True
    assert longevity["dual_m2_storage"] is True


def test_office_laptop_metrics(sample_office_laptop: dict[str, Any]) -> None:
    metrics = compute_laptop_metrics(sample_office_laptop)

    # 1. Mobility & Portability Tier
    mobility = metrics["mobility"]
    assert mobility["portability_tier"] == "ULTRAPORTABLE"
    assert mobility["battery_hours_estimate"] >= 7.0
    assert mobility["portability_score"] >= 80.0

    # 2. Display Optics
    display = metrics["display"]
    assert display["panel_technology"] == "OLED"
    assert display["color_gamut_tier"] == "100% DCI-P3 (Cinema / Pro Creator)"
    assert display["display_score"] >= 80.0

    # 3. AI Copilot+ PC
    silicon = metrics["silicon"]
    assert silicon["is_copilot_plus_pc"] is True
    assert silicon["total_ai_tops"] >= 40.0

    # 4. Ergonomics & Conferencing
    ergonomics = metrics["ergonomics_and_conferencing"]
    assert ergonomics["has_ir_camera"] is True
    assert ergonomics["has_privacy_shutter"] is True
    assert ergonomics["speaker_count"] == 4


def test_benchmark_coverage() -> None:
    assert "Core Ultra 9 285HX" in CPU_BENCHMARK_MAP
    assert "GeForce RTX 5090" in GPU_BENCHMARK_MAP
    assert "Intel Arc 140V" in GPU_BENCHMARK_MAP
