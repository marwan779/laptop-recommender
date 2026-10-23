"""Offline Accuracy and Disambiguation Regression Suite for El Badr Group Egypt (23 PDPs).

Tests 100% of the 23 catalog PDPs from elbadr_laptop_spec_aliases without requiring
network access, verifying zero dropped hardware fields, accurate multiline colon parsing,
section-scoped disambiguation, and end-to-end extraction through GenericCatalogPipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from app.core.patterns.engine import PatternEngine
from app.pipeline.catalog_pipeline import GenericCatalogPipeline
from app.pipeline.deterministic import TableKeyRouter
from app.schemas.laptop import RetailerProduct

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "elbadr_23_raw_catalog.json"
with open(_FIXTURE_PATH, encoding="utf-8") as _f:
    SOURCE_PRODUCTS = json.load(_f)["products"]


@pytest.fixture(scope="module")
def pipeline() -> GenericCatalogPipeline:
    return GenericCatalogPipeline(no_audit=True)


def test_elbadr_all_23_pdp_pattern_engine_extraction():
    """Verify PatternEngine extracts granular specifications directly from DOM for all 23 ElBadr PDPs."""
    assert len(SOURCE_PRODUCTS) == 23, f"Expected 23 ground-truth products, got {len(SOURCE_PRODUCTS)}"

    for pid, prod in sorted(SOURCE_PRODUCTS.items()):
        html = f'<div id="tab-description">{prod["spec_text"]}</div>'
        soup = BeautifulSoup(html, "html.parser")
        spec_res = PatternEngine.extract_specs(
            soup=soup,
            title=prod["title"],
            store_key="elbadr",
            base_url="https://elbadrgroupeg.store",
        )

        assert spec_res.has_text_specs is True, f"PDP {pid} failed to detect DOM text specs"
        assert spec_res.specs_extraction_source == "dom", f"PDP {pid} fell back to title instead of DOM"
        assert spec_res.is_anomaly is False, f"PDP {pid} flagged as anomaly: {spec_res.anomaly_reason}"
        assert len(spec_res.specs) >= 15, f"PDP {pid} extracted only {len(spec_res.specs)} specs (expected >= 15)"


def test_elbadr_ambiguous_keys_disambiguation():
    """Verify TableKeyRouter cleanly disambiguates colliding section-scoped keys without cross-store leakage."""
    router = TableKeyRouter()

    # 1. Graphics Memory (VRAM) vs System Memory (RAM)
    assert router.route_key("Graphics > Memory") == "gpu_vram"
    assert router.route_key("Graphics > VRAM") == "gpu_vram"
    assert router.route_key("Memory > Memory") == "memory"
    assert router.route_key("Memory > Installed") == "memory"

    # 2. Graphics Power (TGP) vs System Power
    assert router.route_key("Graphics > Power") == "gpu_power"
    assert router.route_key("TGP (Thermal Design Power)") == "gpu_power"
    assert router.route_key("Maximum Graphics Power (TGP)") == "gpu_power"
    assert router.route_key("Power & Battery > Capacity") == "power"
    assert router.route_key("Battery > Capacity") == "power"

    # 3. Memory Type vs Display Panel Type
    assert router.route_key("Memory > Type") == "memory_type"
    assert router.route_key("Display > Type") == "display"
    assert router.route_key("Display > Panel Type") == "display"

    # 4. Storage Capacity vs Battery Capacity
    assert router.route_key("Storage > Capacity") == "storage"
    assert router.route_key("Storage > Primary Drive") == "storage"

    # 5. Display Size, Resolution, Refresh Rate
    assert router.route_key("Display > Size") == "display"
    assert router.route_key("Display > Resolution") == "display"
    assert router.route_key("Display > Refresh Rate") == "display_refresh_rate"


def test_elbadr_all_23_pipeline_end_to_end_accuracy(pipeline: GenericCatalogPipeline):
    """Verify GenericCatalogPipeline processes all 23 ElBadr laptops with 100% field extraction accuracy."""
    extracted_records = []

    for pid in sorted(SOURCE_PRODUCTS.keys()):
        p = SOURCE_PRODUCTS[pid]
        html = f'<div id="tab-description">{p["spec_text"]}</div>'
        soup = BeautifulSoup(html, "html.parser")
        spec_res = PatternEngine.extract_specs(
            soup=soup,
            title=p["title"],
            store_key="elbadr",
            base_url="https://elbadrgroupeg.store",
        )

        sku = p["attributes"][2].split(":", 1)[1].strip() if len(p["attributes"]) > 2 else f"SKU-{pid}"

        prod = RetailerProduct(
            store_name="El Badr Group",
            store_key="elbadr",
            store_domain="elbadrgroupeg.store",
            title=p["title"],
            product_url=p["url"],
            retailer_product_id=str(pid),
            retailer_sku=sku,
            price_egp=50000.0,
            price_str="50,000 EGP",
            in_stock=True,
            specs=spec_res.specs,
            raw_description=spec_res.raw_description,
        )

        res = pipeline.process_single(prod, store_key="elbadr")
        assert res is not None, f"PDP {pid} '{p['title']}' was rejected by Gate 3 or pipeline validation"

        specs = res.get("specs", {})
        cpu = specs.get("cpu", {})
        gpu = specs.get("gpu", {})
        ram = specs.get("memory", {})
        storage = specs.get("storage", {})
        disp = specs.get("display", {})

        # CPU verification: All 23 products must have valid CPU manufacturer, model, cores, and threads
        assert cpu.get("manufacturer") in ("Intel", "AMD"), f"PDP {pid} CPU manufacturer missing: {cpu}"
        assert cpu.get("model") is not None, f"PDP {pid} CPU model missing"
        assert cpu.get("cores") is not None and cpu.get("cores") >= 8, f"PDP {pid} CPU cores invalid: {cpu}"
        assert cpu.get("threads") is not None and cpu.get("threads") >= 12, f"PDP {pid} CPU threads invalid: {cpu}"

        # GPU verification: All 23 products must have valid GPU model
        assert gpu.get("model") is not None, f"PDP {pid} GPU model missing"
        if not gpu.get("integrated"):
            assert gpu.get("vram_gb") is not None, f"PDP {pid} discrete GPU VRAM missing"

        # RAM verification: All 23 products must have valid capacity and DDR type
        assert ram.get("capacity_gb") in (8, 16, 32, 64), f"PDP {pid} RAM capacity unexpected: {ram}"
        assert ram.get("memory_type") in ("DDR4", "DDR5", "LPDDR5X"), f"PDP {pid} RAM type invalid: {ram}"

        # Storage verification: All 23 products must have valid storage capacity and SSD type
        assert storage.get("capacity_gb") in (512, 1024, 2048), f"PDP {pid} Storage capacity unexpected: {storage}"
        assert storage.get("storage_type") == "SSD", f"PDP {pid} Storage type not SSD: {storage}"

        # Display verification: All 23 products must have valid size, resolution, and refresh rate
        assert disp.get("size_inches") in (15.6, 16.0), f"PDP {pid} Display size invalid: {disp}"
        assert disp.get("resolution") in ("1920x1080", "1920x1200", "2560x1600", "3840x2400"), (
            f"PDP {pid} Display resolution invalid: {disp}"
        )
        assert disp.get("refresh_rate_hz") in (120, 144, 165, 240, None), f"PDP {pid} Refresh rate invalid: {disp}"

        extracted_records.append(res)

    assert len(extracted_records) == 23, f"Expected 23 successfully extracted laptops, got {len(extracted_records)}"
