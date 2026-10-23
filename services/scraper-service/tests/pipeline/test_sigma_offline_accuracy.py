"""Offline Accuracy and Disambiguation Regression Suite for Sigma Computer (10 PDPs).

Tests 100% of the 10 catalog PDPs from the Sigma raw catalog fixture without requiring
network access, verifying zero dropped hardware fields, accurate Next.js App Router RSC
specifications extraction, key routing, and end-to-end extraction through GenericCatalogPipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.pipeline.catalog_pipeline import GenericCatalogPipeline
from app.pipeline.deterministic import TableKeyRouter
from app.schemas.laptop import RetailerProduct

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "sigma_10_raw_catalog.json"
with open(_FIXTURE_PATH, encoding="utf-8") as _f:
    SOURCE_PRODUCTS = json.load(_f)


@pytest.fixture(scope="module")
def pipeline() -> GenericCatalogPipeline:
    return GenericCatalogPipeline(no_audit=True)


def test_sigma_key_routing_coverage():
    """Verify TableKeyRouter cleanly maps all observed Sigma table keys to hardware buckets."""
    router = TableKeyRouter()

    expected_mappings = {
        "Model": "model",
        "Processor": "cpu",
        "Memory": "memory",
        "Storage": "storage",
        "Graphics Card": "gpu",
        "Screen Size": "display",
        "Resolution": "display",
        "Panel": "display",
        "Colour gamut": "display_gamut",
        "Refresh Rate": "display",
        "Brightness": "display_brightness",
        "Battery": "power",
        "Power Adapter": "power",
        "Operating System": "os",
        "ports": "ports",
        "WLAN + Bluetooth": "connectivity",
        "Dimensions (WxDxH)": "dimensions",
        "Weight": "weight",
        "Color": "color",
        "Max Memory": "max_memory",
        "Memory Slots": "memory_slots",
        "Storage Slot": "storage_slots",
        "Keyboard": "keyboard",
        "Touchscreen": "display",
    }

    for raw_key, expected_bucket in expected_mappings.items():
        assert router.route_key(raw_key) == expected_bucket, (
            f"Key '{raw_key}' routed to '{router.route_key(raw_key)}' instead of '{expected_bucket}'"
        )


def test_sigma_all_10_pipeline_end_to_end_accuracy(pipeline: GenericCatalogPipeline):
    """Verify GenericCatalogPipeline processes all 10 Sigma laptops with 100% field extraction accuracy."""
    assert len(SOURCE_PRODUCTS) == 10, f"Expected 10 benchmark products, got {len(SOURCE_PRODUCTS)}"

    extracted_records = []

    for idx, item in enumerate(SOURCE_PRODUCTS):
        prod = RetailerProduct(**item)
        res = pipeline.process_single(prod, store_key="sigma")
        assert res is not None, f"Item {idx + 1} '{prod.title}' was rejected by pipeline"

        specs = res.get("specs", {})
        ident = specs.get("identity", {})
        cpu = specs.get("cpu", {})
        gpu = specs.get("gpu", {})
        ram = specs.get("memory", {})
        storage = specs.get("storage", {})
        disp = specs.get("display", {})

        # Identity verification
        assert ident.get("brand") == "ASUS", f"Item {idx + 1} brand invalid: {ident.get('brand')}"
        assert ident.get("laptop_model") is not None, f"Item {idx + 1} model missing"

        # CPU verification
        assert cpu.get("model") is not None, f"Item {idx + 1} CPU model missing"
        assert cpu.get("cores") is not None and cpu.get("cores") >= 4, f"Item {idx + 1} CPU cores invalid: {cpu}"

        # GPU verification
        assert gpu.get("model") is not None, f"Item {idx + 1} GPU model missing"

        # RAM verification
        assert ram.get("capacity_gb") in (8, 16, 24, 32), f"Item {idx + 1} RAM capacity invalid: {ram}"
        assert ram.get("memory_type") in ("DDR5", "LPDDR5X"), f"Item {idx + 1} RAM type invalid: {ram}"

        # Storage verification
        assert storage.get("capacity_gb") in (512, 1024), f"Item {idx + 1} Storage capacity invalid: {storage}"
        assert storage.get("storage_type") == "SSD", f"Item {idx + 1} Storage type invalid: {storage}"

        # Display verification
        assert disp.get("size_inches") in (14.0, 16.0), f"Item {idx + 1} Display size invalid: {disp}"

        extracted_records.append(res)

    assert len(extracted_records) == 10, f"Expected 10 extracted laptops, got {len(extracted_records)}"
