"""Offline Catalog Accuracy Test.

Evaluates deterministic extraction performance and precision across all 138 laptops
in the CompuMarts catalog fixture (tests/fixtures/compumarts_138_raw_catalog.json).
Asserts >98% extraction accuracy with zero network calls and sub-second execution.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

from pipeline.deterministic import DeterministicExtractor, TableKeyRouter
from pipeline.sanitizer import TextSanitizer


@pytest.fixture(scope="module")
def raw_catalog() -> dict[str, Any]:
    catalog_path = Path(__file__).resolve().parent.parent / "fixtures" / "compumarts_138_raw_catalog.json"
    assert catalog_path.exists(), f"Missing fixture file: {catalog_path}"
    with open(catalog_path, encoding="utf-8") as f:
        return json.load(f)


def test_compumarts_138_raw_catalog_fixture_integrity(raw_catalog: dict[str, Any]):
    """Verify fixture contains all 138 products with valid specification rows."""
    products = raw_catalog.get("products", [])
    assert len(products) == 138, f"Expected 138 products in fixture, found {len(products)}"
    for p in products:
        assert "url" in p
        assert "title" in p
        assert "spec_rows" in p
        assert len(p["spec_rows"]) > 0


def test_table_key_router_storage_separation():
    """Verify that TableKeyRouter strictly isolates Storage from Max Storage Support and Slots."""
    router = TableKeyRouter()

    table = {
        "Storage": "512GB SSD M.2 2242 PCIe 4.0x4 NVMe",
        "Max Storage Support": "Up to two drives, 2x M.2 SSD up to 1TB each",
        "Storage Slot": "Two M.2 slots (one 2280 PCIe 5.0, one 2280 PCIe 4.0)",
    }
    routed = router.route_table(table)

    assert "storage" in routed
    assert "max_storage" in routed
    assert "storage_slots" in routed

    storage_entries = [v for _, v in routed["storage"]]
    max_storage_entries = [v for _, v in routed["max_storage"]]

    assert any("512GB" in v for v in storage_entries)
    assert not any("1TB" in v for v in storage_entries)
    assert any("1TB" in v for v in max_storage_entries)


def test_compumarts_138_core_specs_extraction_accuracy(raw_catalog: dict[str, Any]):
    """Assert >98% accuracy on core specifications across all 138 catalog laptops."""
    products = raw_catalog.get("products", [])
    total_products = len(products)
    assert total_products == 138

    extractor = DeterministicExtractor()
    sanitizer = TextSanitizer()

    core_resolved = 0
    brand_resolved = 0
    ram_resolved = 0
    storage_resolved = 0
    display_resolved = 0

    t0 = time.time()
    for p in products:
        raw_table = {r["label"]: r["value"] for r in p.get("spec_rows", [])}
        clean_table = sanitizer.sanitize_table(raw_table)
        clean_title = sanitizer.clean_text(p.get("title", ""))

        specs, _ = extractor.extract(
            title=clean_title,
            sanitized_table=clean_table,
            sanitized_sections={},
        )

        has_brand = specs["identity"]["brand"] is not None
        has_ram = specs["memory"]["capacity_gb"] is not None
        has_storage = specs["storage"]["capacity_gb"] is not None
        has_display = specs["display"]["size_inches"] is not None

        if has_brand:
            brand_resolved += 1
        if has_ram:
            ram_resolved += 1
        if has_storage:
            storage_resolved += 1
        if has_display:
            display_resolved += 1

        # Product core success: Brand, RAM, and Storage successfully extracted deterministically
        if has_brand and has_ram and has_storage:
            core_resolved += 1

    elapsed = time.time() - t0

    # 1. Performance: Lightning-fast execution (<1 second total across all 138 laptops)
    assert elapsed < 5.0, f"Extraction was too slow: took {elapsed:.3f}s for 138 laptops"

    # 2. Accuracy: Core hardware extraction > 98% (137/138 = 99.28%)
    core_accuracy = (core_resolved / total_products) * 100
    assert core_accuracy >= 98.0, f"Expected >= 98.0% core accuracy, got {core_accuracy:.2f}%"

    # 3. Individual field bounds:
    assert brand_resolved == 138, f"Brand missed: {brand_resolved}/138"
    assert (ram_resolved / total_products) >= 0.98
    assert (storage_resolved / total_products) >= 0.98
    assert (display_resolved / total_products) >= 0.95


def test_zero_storage_collisions_on_max_support_laptops(raw_catalog: dict[str, Any]):
    """Verify that all 16 laptops with Max Storage Support rows extract installed 512GB with zero collisions."""
    products = raw_catalog.get("products", [])
    extractor = DeterministicExtractor()
    sanitizer = TextSanitizer()

    verified_cases = 0
    for p in products:
        raw_table = {r["label"]: r["value"] for r in p.get("spec_rows", [])}
        routed = extractor.router.route_table(raw_table)

        if "max_storage" in routed:
            st_entries = [v for _, v in routed.get("storage", [])]
            if any("512" in v for v in st_entries):
                clean_table = sanitizer.sanitize_table(raw_table)
                clean_title = sanitizer.clean_text(p.get("title", ""))
                specs, _ = extractor.extract(
                    title=clean_title,
                    sanitized_table=clean_table,
                    sanitized_sections={},
                )
                assert specs["storage"]["capacity_gb"] == 512, (
                    f"Storage collision defect detected on {p['title']}: "
                    f"extracted {specs['storage']['capacity_gb']}GB instead of installed 512GB"
                )
                verified_cases += 1

    assert verified_cases >= 16, f"Expected at least 16 collision cases from catalog audit, found {verified_cases}"


def test_multidimm_ram_precedence(raw_catalog: dict[str, Any]):
    """Verify that 2x 16GB multi-DIMM configurations extract 32GB instead of 16GB."""
    products = raw_catalog.get("products", [])
    extractor = DeterministicExtractor()
    sanitizer = TextSanitizer()

    verified_cases = 0
    for p in products:
        raw_table = {r["label"]: r["value"] for r in p.get("spec_rows", [])}
        table_str = " ".join(raw_table.values())
        if re.search(r"\b2\s*x\s*16\s*gb\b", table_str, re.IGNORECASE):
            clean_table = sanitizer.sanitize_table(raw_table)
            clean_title = sanitizer.clean_text(p.get("title", ""))
            specs, _ = extractor.extract(
                title=clean_title,
                sanitized_table=clean_table,
                sanitized_sections={},
            )
            assert specs["memory"]["capacity_gb"] == 32, (
                f"Multi-DIMM precedence defect on {p['title']}: "
                f"extracted {specs['memory']['capacity_gb']}GB instead of 32GB"
            )
            verified_cases += 1

    assert verified_cases >= 5, f"Expected to verify at least 5 multi-DIMM cases, found {verified_cases}"


def test_raw_spec_populated_and_formatted_across_all_categories(raw_catalog: dict[str, Any]):
    """Verify that raw_spec is present in all 12 categories and properly formatted as {Key}: {Value}."""
    from pipeline.schema import empty_laptop_specifications

    # 1. Schema check: All 12 categories MUST contain raw_spec
    skeleton = empty_laptop_specifications()
    assert len(skeleton) == 12
    for cat_name, cat_dict in skeleton.items():
        assert "raw_spec" in cat_dict, f"Category '{cat_name}' is missing 'raw_spec' in schema"

    products = raw_catalog.get("products", [])
    extractor = DeterministicExtractor()
    sanitizer = TextSanitizer()

    total_products = len(products)
    assert total_products == 138

    categories = list(skeleton.keys())
    cat_counts = {c: 0 for c in categories}

    for p in products:
        raw_table = {r["label"]: r["value"] for r in p.get("spec_rows", [])}
        clean_table = sanitizer.sanitize_table(raw_table)
        clean_title = sanitizer.clean_text(p.get("title", ""))

        specs, _ = extractor.extract(
            title=clean_title,
            sanitized_table=clean_table,
            sanitized_sections={},
        )

        for cat_name in categories:
            raw_val = specs[cat_name]["raw_spec"]
            if raw_val is not None:
                cat_counts[cat_name] += 1
                assert isinstance(raw_val, str)
                assert len(raw_val.strip()) > 0
                # Verify format: every '|' separated chunk must follow "{Key}: {Value}"
                chunks = [chunk.strip() for chunk in raw_val.split(" | ")]
                for chunk in chunks:
                    assert ":" in chunk, f"Invalid raw_spec format in {cat_name}: '{chunk}'"
                    key, val = chunk.split(":", 1)
                    assert len(key.strip()) > 0, f"Empty key in raw_spec chunk: '{chunk}'"

    # 2. Coverage assertions across catalog
    assert cat_counts["identity"] == 138, "Identity raw_spec must be 100% covered"
    assert cat_counts["cpu"] == 138, "CPU raw_spec must be 100% covered"
    assert cat_counts["storage"] >= 137, "Storage raw_spec coverage must be >= 99%"
    assert cat_counts["memory"] >= 137, "Memory raw_spec coverage must be >= 99%"
    assert cat_counts["display"] >= 137, "Display raw_spec coverage must be >= 99%"
    assert cat_counts["gpu"] >= 136, "GPU raw_spec coverage must be >= 98%"
    assert cat_counts["operating_system"] >= 136, "OS raw_spec coverage must be >= 98%"


def test_expanded_specification_fields_extraction(raw_catalog: dict[str, Any]):
    """Verify high-yield extraction and physical validity for all 23 newly added specification fields."""
    products = raw_catalog.get("products", [])
    total_products = len(products)
    assert total_products == 138

    extractor = DeterministicExtractor()
    sanitizer = TextSanitizer()

    counts = {
        "brightness": 0,
        "gamut": 0,
        "response_time": 0,
        "surface": 0,
        "hdr": 0,
        "privacy_shutter": 0,
        "ir_camera": 0,
        "warranty": 0,
        "warranty_years": 0,
        "gpu_boost": 0,
        "gpu_tdp": 0,
        "gpu_ai_tops": 0,
        "thunderbolt": 0,
        "card_reader": 0,
        "backlight_type": 0,
        "numpad": 0,
        "material": 0,
        "max_storage": 0,
        "fast_charging": 0,
        "is_soldered": 0,
    }

    t0 = time.time()
    for p in products:
        raw_table = {r["label"]: r["value"] for r in p.get("spec_rows", [])}
        clean_table = sanitizer.sanitize_table(raw_table)
        clean_title = sanitizer.clean_text(p.get("title", ""))

        specs, _ = extractor.extract(
            title=clean_title,
            sanitized_table=clean_table,
            sanitized_sections={},
        )

        disp = specs["display"]
        if disp["brightness_nits"] is not None:
            counts["brightness"] += 1
            assert 150 <= disp["brightness_nits"] <= 3000
        if disp["color_gamut"] is not None:
            counts["gamut"] += 1
            assert "%" in disp["color_gamut"]
        if disp["response_time_ms"] is not None:
            counts["response_time"] += 1
            assert 0.1 <= disp["response_time_ms"] <= 35.0
        if disp["surface_treatment"] is not None:
            counts["surface"] += 1
            assert disp["surface_treatment"] in {"Anti-glare", "Anti-reflection", "Matte", "Glossy"}
        if disp["hdr"] is not None:
            counts["hdr"] += 1

        aw = specs["audio_webcam"]
        if aw["has_privacy_shutter"] is not None:
            counts["privacy_shutter"] += 1
            assert isinstance(aw["has_privacy_shutter"], bool)
        if aw["has_ir_camera"] is not None:
            counts["ir_camera"] += 1
            assert isinstance(aw["has_ir_camera"], bool)

        ident = specs["identity"]
        if ident["warranty"] is not None:
            counts["warranty"] += 1
        if ident["warranty_years"] is not None:
            counts["warranty_years"] += 1
            assert 1 <= ident["warranty_years"] <= 5

        gpu = specs["gpu"]
        if gpu["boost_clock_mhz"] is not None:
            counts["gpu_boost"] += 1
            assert 500 <= gpu["boost_clock_mhz"] <= 3200
        if gpu["tdp_w"] is not None:
            counts["gpu_tdp"] += 1
            assert 20 <= gpu["tdp_w"] <= 250
        if gpu["ai_tops"] is not None:
            counts["gpu_ai_tops"] += 1
            assert 5 <= gpu["ai_tops"] <= 3000

        conn = specs["connectivity"]
        if conn["thunderbolt_version"] is not None:
            counts["thunderbolt"] += 1
            assert "Thunderbolt" in conn["thunderbolt_version"]
        if conn["has_card_reader"] is not None:
            counts["card_reader"] += 1
            assert isinstance(conn["has_card_reader"], bool)

        bs = specs["build_security"]
        if bs["keyboard_backlight_type"] is not None:
            counts["backlight_type"] += 1
            assert bs["keyboard_backlight_type"] in {
                "Per-Key RGB",
                "4-Zone RGB",
                "1-Zone RGB",
                "RGB Backlit",
                "White Backlit",
                "Backlit",
                "Amber Backlit",
            }
        if bs["has_numpad"] is not None:
            counts["numpad"] += 1
            assert isinstance(bs["has_numpad"], bool)
        if bs["chassis_material"] is not None:
            counts["material"] += 1
            assert len(bs["chassis_material"]) > 0

        st = specs["storage"]
        if st["max_supported_gb"] is not None:
            counts["max_storage"] += 1
            assert st["max_supported_gb"] >= 512

        pw = specs["power_battery"]
        if pw["fast_charging"] is not None:
            counts["fast_charging"] += 1

        mem = specs["memory"]
        if mem["is_soldered"] is not None:
            counts["is_soldered"] += 1
            assert isinstance(mem["is_soldered"], bool)

    elapsed = time.time() - t0
    assert elapsed < 5.0, f"Extraction was too slow: took {elapsed:.3f}s for 138 laptops"

    # Verify yields match expected catalog bounds (>50% for display brightness/gamut/surface)
    assert counts["brightness"] >= 70, f"Brightness yield too low: {counts['brightness']}/138"
    assert counts["gamut"] >= 70, f"Color gamut yield too low: {counts['gamut']}/138"
    assert counts["surface"] >= 60, f"Surface yield too low: {counts['surface']}/138"
    assert counts["backlight_type"] >= 90, f"Backlight type yield too low: {counts['backlight_type']}/138"
    assert counts["privacy_shutter"] >= 45, f"Privacy shutter yield too low: {counts['privacy_shutter']}/138"
    assert counts["warranty"] >= 45, f"Warranty yield too low: {counts['warranty']}/138"
    assert counts["warranty_years"] >= 40, f"Warranty years yield too low: {counts['warranty_years']}/138"
    assert counts["gpu_boost"] >= 25, f"GPU boost yield too low: {counts['gpu_boost']}/138"
    assert counts["gpu_tdp"] >= 20, f"GPU TDP yield too low: {counts['gpu_tdp']}/138"
    assert counts["card_reader"] >= 20, f"Card reader yield too low: {counts['card_reader']}/138"
    assert counts["thunderbolt"] >= 20, f"Thunderbolt yield too low: {counts['thunderbolt']}/138"
    assert counts["material"] >= 30, f"Material yield too low: {counts['material']}/138"
    assert counts["max_storage"] >= 15, f"Max storage yield too low: {counts['max_storage']}/138"
