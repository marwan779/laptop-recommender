"""Unit tests for the Deterministic Hardware Metrics Engine and Enrichment Service."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.catalog_metrics_service import CatalogMetricsService
from app.services.metrics_engine import (
    calculate_all_hardware_metrics,
    calculate_display_metrics,
    calculate_economics_metrics,
    calculate_longevity_metrics,
    calculate_mobility_metrics,
    calculate_silicon_and_power_metrics,
    clamp,
    resolve_cpu_benchmark,
    resolve_gpu_benchmark,
)


@pytest.fixture
def sample_cpu_benchmarks() -> dict[str, Any]:
    return {
        "intel_core_i7_13700h": {
            "model": "Core i7-13700H",
            "base_score": 95.0,
            "base_power_w": 45,
            "aliases": ["core i7-13700h", "i7-13700h", "13700h"],
        },
        "amd_ryzen_7_7735hs": {
            "model": "Ryzen 7 7735HS",
            "base_score": 82.0,
            "base_power_w": 35,
            "aliases": ["ryzen 7 7735hs", "7735hs"],
        },
    }


@pytest.fixture
def sample_gpu_benchmarks() -> dict[str, Any]:
    return {
        "RTX_4060_8GB": {
            "model": "GeForce RTX 4060",
            "base_score": 10500.0,
            "tdp_limits": {"min_w": 35, "max_w": 140},
            "match_patterns": ["rtx 4060", "geforce rtx 4060", "rtx 4060 laptop gpu"],
        },
        "RTX_3050_6GB": {
            "model": "GeForce RTX 3050",
            "base_score": 5200.0,
            "tdp_limits": {"min_w": 35, "max_w": 75},
            "match_patterns": ["rtx 3050", "geforce rtx 3050 6gb"],
        },
    }


def test_clamp() -> None:
    assert clamp(50.0, 0.0, 100.0) == 50.0
    assert clamp(-10.0, 0.0, 100.0) == 0.0
    assert clamp(150.0, 0.0, 100.0) == 100.0


def test_resolve_gpu_and_cpu_benchmarks(
    sample_cpu_benchmarks: dict[str, Any],
    sample_gpu_benchmarks: dict[str, Any],
) -> None:
    gpu_spec = {"model": "GeForce RTX 4060", "integrated": False}
    score, t_min, t_max = resolve_gpu_benchmark(gpu_spec, sample_gpu_benchmarks)
    assert score == 10500.0
    assert t_min == 35.0
    assert t_max == 140.0

    cpu_spec = {"model": "Core i7-13700H"}
    c_score, c_power = resolve_cpu_benchmark(cpu_spec, sample_cpu_benchmarks)
    assert c_score == 95.0
    assert c_power == 45.0


def test_metric_1_effective_gpu_normalization_and_inference(
    sample_cpu_benchmarks: dict[str, Any],
    sample_gpu_benchmarks: dict[str, Any],
) -> None:
    # Case A: Explicit tdp_w (140W)
    cpu_spec = {"model": "Core i7-13700H", "base_power_w": 45}
    gpu_spec = {"model": "GeForce RTX 4060", "tdp_w": 140, "integrated": False}
    power_spec = {"power_adapter_w": 240}

    silicon, power = calculate_silicon_and_power_metrics(
        cpu_spec=cpu_spec,
        gpu_spec=gpu_spec,
        power_spec=power_spec,
        cpu_benchmarks=sample_cpu_benchmarks,
        gpu_benchmarks=sample_gpu_benchmarks,
    )

    # 10500 * 1.0 / 100 = 105.0
    assert silicon["effective_gpu_score"] == 105.0
    assert silicon["inferred_tgp_w"] == 140.0
    assert silicon["tgp_source"] == "EXPLICIT_SPEC"
    assert power["delta_p_watts"] == 30.0  # 240 - (45 + 140 + 25)
    assert power["electrical_status"] == "UNCONSTRAINED_HEADROOM"

    # Case B: gpu.tdp_w is NULL -> Infer from charger (120W - 45 - 25 = 50W)
    gpu_spec_no_tdp = {"model": "GeForce RTX 4060", "tdp_w": None, "integrated": False}
    power_spec_budget = {"power_adapter_w": 120}

    silicon_b, power_b = calculate_silicon_and_power_metrics(
        cpu_spec=cpu_spec,
        gpu_spec=gpu_spec_no_tdp,
        power_spec=power_spec_budget,
        cpu_benchmarks=sample_cpu_benchmarks,
        gpu_benchmarks=sample_gpu_benchmarks,
    )

    assert silicon_b["tgp_source"] == "INFERRED_FROM_CHARGER"
    assert silicon_b["inferred_tgp_w"] == 50.0  # 120 - 45 - 25 = 50W
    # scale = 0.72 + 0.28 * (50-35)/(140-35) = 0.72 + 0.28 * (15/105) = 0.72 + 0.04 = 0.76
    # 10500 * 0.76 / 100 = 79.8
    assert silicon_b["effective_gpu_score"] == pytest.approx(79.8, abs=0.2)


def test_metric_2_null_power_adapter_guard(
    sample_cpu_benchmarks: dict[str, Any],
    sample_gpu_benchmarks: dict[str, Any],
) -> None:
    """When power_adapter_w is null, Scale_Factor_CPU = 1.0 and Delta P = 0.0."""
    cpu_spec = {"model": "Core i7-13700H"}
    gpu_spec = {"model": "GeForce RTX 4060", "integrated": False}
    power_spec = {"power_adapter_w": None}

    silicon, power = calculate_silicon_and_power_metrics(
        cpu_spec=cpu_spec,
        gpu_spec=gpu_spec,
        power_spec=power_spec,
        cpu_benchmarks=sample_cpu_benchmarks,
        gpu_benchmarks=sample_gpu_benchmarks,
    )

    assert silicon["scale_factor_cpu"] == 1.0
    assert silicon["effective_cpu_score"] == 95.0  # base 95.0 * 1.0
    assert power["delta_p_watts"] == 0.0
    assert power["electrical_status"] == "UNKNOWN_CHARGER_NEUTRAL"


def test_metric_3_display_optics() -> None:
    # High-end display: 14" 2.8K OLED 120Hz 16:10 100% DCI-P3
    display_high = {
        "resolution_width": 2880,
        "resolution_height": 1800,
        "size_inches": 14.0,
        "refresh_rate_hz": 120,
        "panel_type": "OLED",
        "color_gamut": "100% DCI-P3",
        "aspect_ratio": "16:10",
    }
    m_high = calculate_display_metrics(display_high)
    assert m_high["ppi"] == pytest.approx(242.6, abs=0.5)
    assert m_high["display_score"] > 80.0
    assert m_high["panel_technology"] == "OLED"
    assert m_high["color_gamut_tier"] == "PROFESSIONAL_DCI_P3"

    # Budget display: 15.6" 1080p TN 60Hz 16:9 45% NTSC
    display_budget = {
        "resolution_width": 1920,
        "resolution_height": 1080,
        "size_inches": 15.6,
        "refresh_rate_hz": 60,
        "panel_type": "TN",
        "color_gamut": "45% NTSC",
        "aspect_ratio": "16:9",
    }
    m_budget = calculate_display_metrics(display_budget)
    assert m_budget["ppi"] == pytest.approx(141.2, abs=0.5)
    assert m_budget["display_score"] < 45.0
    assert m_budget["color_gamut_tier"] == "BUDGET_WASHED"


def test_metric_4_mobility_and_portability_guards() -> None:
    # Guard 3: battery_capacity_wh is null -> fallback 50.0 Wh
    # Guard 3: height_mm is null -> 100% weight on weight_kg
    power_null = {"battery_capacity_wh": None}
    physical_no_height = {"weight_kg": 1.5, "height_mm": None}

    m = calculate_mobility_metrics(power_null, physical_no_height, cpu_base_w=45.0)
    assert m["battery_capacity_wh"] == 50.0
    assert m["battery_hours_estimate"] == round(50.0 / (6.0 + 45.0 * 0.20), 2)
    # 100 - (100 * (1.5 - 1.0)/2.5) = 100 - (100 * 0.2) = 80.0
    assert m["portability_score"] == 80.0
    assert m["portability_tier"] == "ULTRAPORTABLE"

    # Guard 3: weight_kg is null -> default 50.0
    physical_null = {"weight_kg": None, "height_mm": None}
    m_null = calculate_mobility_metrics(power_null, physical_null, cpu_base_w=45.0)
    assert m_null["portability_score"] == 50.0
    assert m_null["portability_tier"] == "BALANCED"


def test_metric_5_upgradeability_score() -> None:
    # Max upgradeability: 2x SODIMM (45) + 2x M.2 (35) + Thunderbolt 4 (20) = 100
    memory_max = {"is_soldered": False, "slot_count": 2, "capacity_gb": 16}
    storage_max = {"slot_count": 2}
    conn_max = {"thunderbolt_version": "Thunderbolt 4"}
    m_max = calculate_longevity_metrics(memory_max, storage_max, conn_max)
    assert m_max["upgradeability_score"] == 100.0
    assert m_max["upgradeability_tier"] == "MAXIMUM_UPGRADEABLE"

    # Soldered 8GB appliance: Soldered <= 8GB (0) + 1x M.2 (20) + Basic USB (0) = 20
    memory_locked = {"is_soldered": True, "slot_count": 0, "capacity_gb": 8}
    storage_min = {"slot_count": 1}
    conn_basic = {"thunderbolt_version": None, "ports": ["USB 3.2 Gen 1 Type-A"]}
    m_locked = calculate_longevity_metrics(memory_locked, storage_min, conn_basic)
    assert m_locked["upgradeability_score"] == 20.0
    assert m_locked["upgradeability_tier"] == "LOCKED_APPLIANCE"


def test_metric_6_economics_and_value_ratio() -> None:
    offers = [
        {"store": "Store A", "price_egp": 55000.0, "is_available": True},
        {"store": "Store B", "price_egp": 50000.0, "is_available": True},
        {"store": "Store C", "price_egp": 60000.0, "is_available": True},
    ]

    m = calculate_economics_metrics(
        offers=offers,
        effective_gpu_score=105.0,
        effective_cpu_score=90.0,
        ram_gb=16,
    )

    assert m["min_price_egp"] == 50000.0
    assert m["cheapest_store"] == "Store B"
    assert m["max_price_egp"] == 60000.0
    assert m["price_spread_egp"] == 10000.0
    # hardware_composite = 105.0 + 90.0 + (16 * 1.5) = 219.0
    # value_ratio = (219.0 / 50000.0) * 100000.0 = 438.0
    assert m["value_ratio"] == 438.0


def test_calculate_all_hardware_metrics(
    sample_cpu_benchmarks: dict[str, Any],
    sample_gpu_benchmarks: dict[str, Any],
) -> None:
    laptop = {
        "canonical_id": "laptop_test_1",
        "specs": {
            "cpu": {"model": "Core i7-13700H", "base_power_w": 45},
            "gpu": {"model": "GeForce RTX 4060", "tdp_w": 140, "integrated": False},
            "power_battery": {"power_adapter_w": 240, "battery_capacity_wh": 70},
            "display": {"resolution_width": 1920, "resolution_height": 1080, "size_inches": 15.6},
            "memory": {"is_soldered": False, "slot_count": 2, "capacity_gb": 16},
            "storage": {"slot_count": 2},
            "connectivity": {"thunderbolt_version": "Thunderbolt 4"},
            "physical": {"weight_kg": 2.2, "height_mm": 20.0},
        },
        "offers": [{"store": "Compumarts", "price_egp": 50000, "is_available": True}],
    }

    result = calculate_all_hardware_metrics(laptop, sample_cpu_benchmarks, sample_gpu_benchmarks)
    assert "silicon" in result
    assert "power" in result
    assert "display" in result
    assert "mobility" in result
    assert "longevity" in result
    assert "economics" in result
    assert result["silicon"]["effective_gpu_score"] == 105.0
    assert result["economics"]["value_ratio"] is not None


def test_catalog_metrics_service_enrichment(tmp_path: Path) -> None:
    dummy_catalog = {
        "title": "Test Catalog",
        "laptops": [
            {
                "canonical_id": "test_laptop_1",
                "specs": {
                    "cpu": {"model": "Core i7-13700H"},
                    "gpu": {"model": "GeForce RTX 4060"},
                    "power_battery": {"power_adapter_w": 230, "battery_capacity_wh": 80},
                },
                "offers": [{"store": "Sigma", "price_egp": 52000, "is_available": True}],
            }
        ],
    }

    catalog_file = tmp_path / "test_catalog.json"
    catalog_file.write_text(json.dumps(dummy_catalog), encoding="utf-8")

    service = CatalogMetricsService()
    summary = service.enrich_catalog(catalog_path=catalog_file, overwrite=True)

    assert summary["total_laptops"] == 1
    assert summary["processed_successfully"] == 1
    assert summary["averages"]["effective_gpu_score"] > 0

    # Verify file was enriched in-place
    saved_data = json.loads(catalog_file.read_text(encoding="utf-8"))
    assert "hardware_metrics" in saved_data["laptops"][0]
    assert "metrics_calculated_at" in saved_data

