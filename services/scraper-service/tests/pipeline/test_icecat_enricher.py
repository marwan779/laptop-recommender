"""Unit tests for Icecat Search, OpenIcecat JSON API Parser, and Catalog Enricher."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.matching.models import CanonicalLaptop, StoreOffer, UnifiedCatalog
from app.pipeline.icecat.api_service import IcecatAPIService
from app.pipeline.icecat.enricher import IcecatCatalogEnricher
from app.pipeline.icecat.search_service import (
    build_search_queries,
    evaluate_spec_match,
    extract_clean_family,
)
from app.pipeline.orchestrator import LaptopExtractionPipeline
from app.pipeline.schema import RawScrapedProduct


SAMPLE_OPENICECAT_LEGION_JSON: dict[str, Any] = {
    "GeneralInfo": {"IcecatId": 132391784},
    "FeaturesGroups": [
        {
            "FeatureGroup": {"Name": {"Value": "Design"}},
            "Features": [
                {
                    "Feature": {"Name": {"Value": "Colour name"}},
                    "PresentationValue": "Eclipse Black",
                    "RawValue": "Eclipse Black",
                },
                {
                    "Feature": {"Name": {"Value": "Housing material"}},
                    "PresentationValue": "ABS, Aluminium",
                    "RawValue": "ABS,Aluminium",
                },
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Display"}},
            "Features": [
                {
                    "Feature": {"Name": {"Value": "Display diagonal"}},
                    "PresentationValue": '38.4 cm (15.1")',
                    "RawValue": "15.1",
                },
                {
                    "Feature": {"Name": {"Value": "Display resolution"}},
                    "PresentationValue": "2560 x 1600 pixels",
                    "RawValue": "2560 x 1600",
                },
                {"Feature": {"Name": {"Value": "Touchscreen"}}, "PresentationValue": "No", "RawValue": "N"},
                {"Feature": {"Name": {"Value": "Panel type"}}, "PresentationValue": "OLED", "RawValue": "OLED"},
                {
                    "Feature": {"Name": {"Value": "Native aspect ratio"}},
                    "PresentationValue": "16:10",
                    "RawValue": "16:10",
                },
                {
                    "Feature": {"Name": {"Value": "Display brightness"}},
                    "PresentationValue": "500 cd/m²",
                    "RawValue": "500",
                },
                {
                    "Feature": {"Name": {"Value": "RGB colour space"}},
                    "PresentationValue": "DCI-P3",
                    "RawValue": "DCI-P3",
                },
                {"Feature": {"Name": {"Value": "Colour gamut"}}, "PresentationValue": "100%", "RawValue": "100"},
                {
                    "Feature": {"Name": {"Value": "Maximum refresh rate"}},
                    "PresentationValue": "165 Hz",
                    "RawValue": "165",
                },
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Processor"}},
            "Features": [
                {"Feature": {"Name": {"Value": "Processor base power"}}, "PresentationValue": "55 W", "RawValue": "55"},
                {
                    "Feature": {"Name": {"Value": "Maximum turbo power"}},
                    "PresentationValue": "160 W",
                    "RawValue": "160",
                },
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Neural processor unit (NPU)"}},
            "Features": [
                {
                    "Feature": {"Name": {"Value": "NPU performance up to"}},
                    "PresentationValue": "13 TOPs",
                    "RawValue": "13",
                },
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Memory"}},
            "Features": [
                {"Feature": {"Name": {"Value": "Internal memory"}}, "PresentationValue": "32 GB", "RawValue": "32"},
                {
                    "Feature": {"Name": {"Value": "Internal memory type"}},
                    "PresentationValue": "DDR5-SDRAM",
                    "RawValue": "DDR5-SDRAM",
                },
                {
                    "Feature": {"Name": {"Value": "Memory clock speed"}},
                    "PresentationValue": "5600 MHz",
                    "RawValue": "5600",
                },
                {
                    "Feature": {"Name": {"Value": "Memory slots"}},
                    "PresentationValue": "2x SO-DIMM",
                    "RawValue": "2x SO-DIMM",
                },
                {
                    "Feature": {"Name": {"Value": "Maximum internal memory"}},
                    "PresentationValue": "32 GB",
                    "RawValue": "32",
                },
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Storage"}},
            "Features": [
                {
                    "Feature": {"Name": {"Value": "Total storage capacity"}},
                    "PresentationValue": "512 GB",
                    "RawValue": "512",
                },
                {"Feature": {"Name": {"Value": "Storage media"}}, "PresentationValue": "SSD", "RawValue": "SSD"},
                {
                    "Feature": {"Name": {"Value": "SSD interface"}},
                    "PresentationValue": "PCI Express 4.0",
                    "RawValue": "PCI Express 4.0",
                },
                {"Feature": {"Name": {"Value": "NVMe"}}, "PresentationValue": "Yes", "RawValue": "Y"},
                {"Feature": {"Name": {"Value": "SSD form factor"}}, "PresentationValue": "M.2", "RawValue": "M.2"},
                {"Feature": {"Name": {"Value": "Number of SSDs installed"}}, "PresentationValue": "1", "RawValue": "1"},
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Graphics"}},
            "Features": [
                {
                    "Feature": {"Name": {"Value": "Discrete graphics memory type"}},
                    "PresentationValue": "GDDR7",
                    "RawValue": "GDDR7",
                },
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Battery"}},
            "Features": [
                {"Feature": {"Name": {"Value": "Battery capacity"}}, "PresentationValue": "80 Wh", "RawValue": "80"},
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Power"}},
            "Features": [
                {"Feature": {"Name": {"Value": "AC adapter power"}}, "PresentationValue": "245 W", "RawValue": "245"},
                {
                    "Feature": {"Name": {"Value": "USB Power Delivery (USB PD)"}},
                    "PresentationValue": "Yes",
                    "RawValue": "Y",
                },
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Weight & dimensions"}},
            "Features": [
                {"Feature": {"Name": {"Value": "Width"}}, "PresentationValue": "344.9 mm", "RawValue": "344.9"},
                {"Feature": {"Name": {"Value": "Depth"}}, "PresentationValue": "255.3 mm", "RawValue": "255.35"},
                {"Feature": {"Name": {"Value": "Height (rear)"}}, "PresentationValue": "2.15 cm", "RawValue": "21.54"},
                {"Feature": {"Name": {"Value": "Weight"}}, "PresentationValue": "1.9 kg", "RawValue": "1900"},
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Ports & interfaces"}},
            "Features": [
                {
                    "Feature": {"Name": {"Value": "USB 3.2 Gen 1 (3.1 Gen 1) Type-A ports quantity"}},
                    "PresentationValue": "3",
                    "RawValue": "3",
                },
                {
                    "Feature": {"Name": {"Value": "Thunderbolt 4 ports quantity"}},
                    "PresentationValue": "1",
                    "RawValue": "1",
                },
                {"Feature": {"Name": {"Value": "HDMI ports quantity"}}, "PresentationValue": "1", "RawValue": "1"},
                {"Feature": {"Name": {"Value": "HDMI version"}}, "PresentationValue": "2.1", "RawValue": "2.1"},
            ],
        },
        {
            "FeatureGroup": {"Name": {"Value": "Keyboard"}},
            "Features": [
                {"Feature": {"Name": {"Value": "Keyboard backlit"}}, "PresentationValue": "Yes", "RawValue": "Y"},
                {
                    "Feature": {"Name": {"Value": "Keyboard backlit zone"}},
                    "PresentationValue": "24-zone RGB",
                    "RawValue": "24-zone RGB",
                },
                {
                    "Feature": {"Name": {"Value": "Keyboard language"}},
                    "PresentationValue": "French",
                    "RawValue": "French",
                },
            ],
        },
    ],
}


def test_parse_openicecat_json_maps_all_11_categories() -> None:
    """Verify IcecatAPIService accurately parses all 21 feature groups into our 11-category schema."""
    api = IcecatAPIService(request_delay=0.0)
    parsed = api.parse_product_json(SAMPLE_OPENICECAT_LEGION_JSON)

    assert parsed["identity"]["color"] == "Eclipse Black"
    assert parsed["cpu"]["tdp_w"] == 55.0
    assert parsed["cpu"]["max_turbo_power_w"] == 160.0
    assert parsed["cpu"]["npu_tops"] == 13.0
    assert parsed["gpu"]["vram_type"] == "GDDR7"

    assert parsed["memory"]["capacity_gb"] == 32
    assert parsed["memory"]["memory_type"] == "DDR5"
    assert parsed["memory"]["speed"] == "5600 MHz"
    assert parsed["memory"]["slot_count"] == 2
    assert parsed["memory"]["max_supported_gb"] == 32
    assert parsed["memory"]["is_soldered"] is False

    assert parsed["storage"]["capacity_gb"] == 512
    assert parsed["storage"]["storage_type"] == "SSD"
    assert parsed["storage"]["interface"] == "PCIe NVMe"
    assert parsed["storage"]["form_factor"] == "M.2"
    assert parsed["storage"]["slot_count"] == 1

    assert parsed["display"]["size_inches"] == 15.1
    assert parsed["display"]["resolution"] == "2560x1600"
    assert parsed["display"]["refresh_rate_hz"] == 165
    assert parsed["display"]["panel_type"] == "OLED"
    assert parsed["display"]["aspect_ratio"] == "16:10"
    assert parsed["display"]["touchscreen"] is False
    assert parsed["display"]["brightness_nits"] == 500
    assert parsed["display"]["color_gamut"] == "100% DCI-P3"

    assert parsed["power_battery"]["battery_capacity_wh"] == 80.0
    assert parsed["power_battery"]["power_adapter_w"] == 245.0
    assert parsed["power_battery"]["fast_charging"] is True

    assert parsed["physical"]["weight_kg"] == 1.9
    assert parsed["physical"]["width_mm"] == 344.9
    assert parsed["physical"]["depth_mm"] == 255.3
    assert parsed["physical"]["height_mm"] == 21.5

    assert parsed["connectivity"]["thunderbolt_version"] == "Thunderbolt 4"
    assert "3x USB 3.2 Gen 1 Type-A" in parsed["connectivity"]["ports"]
    assert "1x Thunderbolt 4" in parsed["connectivity"]["ports"]
    assert "1x HDMI 2.1" in parsed["connectivity"]["ports"]

    assert parsed["build_security"]["has_backlit_keyboard"] is True
    assert parsed["build_security"]["keyboard_backlight_type"] == "24-zone RGB"
    assert parsed["build_security"]["chassis_material"] == "ABS, Aluminium"


def test_ownership_matrix_exact_vs_variant_match() -> None:
    """Verify EXACT_MATCH overwrites all non-regional/non-dict fields while VARIANT_MATCH preserves store RAM/Storage/Display."""
    api = IcecatAPIService(request_delay=0.0)
    icecat_specs = api.parse_product_json(SAMPLE_OPENICECAT_LEGION_JSON)

    # 1. Test EXACT_MATCH: Preserves CPU/GPU dicts & OS, overwrites display/battery/physical/memory/storage
    exact_laptop = CanonicalLaptop(
        canonical_id="laptop_lenovo_legion_exact",
        mpn="83F0006ELK",
        brand="Lenovo",
        laptop_family="Legion",
        laptop_model="Legion 5 15IAX10",
        title="Lenovo Legion 5 15IAX10",
        specs={
            "identity": {"brand": "Lenovo", "color": None},
            "cpu": {"manufacturer": "Intel", "model": "Core Ultra 7 255HX", "cores": 20, "tdp_w": None},
            "gpu": {"manufacturer": "NVIDIA", "model": "GeForce RTX 5060", "vram_gb": 8, "integrated": False},
            "memory": {"capacity_gb": 32, "memory_type": None},
            "storage": {"capacity_gb": 512, "interface": None},
            "display": {"size_inches": 15.1, "panel_type": "IPS"},  # Noisy store value "IPS"
            "operating_system": {"name": "FreeDOS"},  # Regional Egyptian OS
        },
        offers=[
            StoreOffer(
                store_key="compumarts",
                store_name="CompuMarts",
                product_url="https://compumarts.com/legion",
                title="Lenovo Legion 5",
                price_egp=68000.0,
            )
        ],
    )

    IcecatCatalogEnricher.apply_icecat_specs_to_laptop(exact_laptop, icecat_specs, "EXACT_MATCH")
    # CPU dictionary cores kept, missing tdp_w injected from Icecat
    assert exact_laptop.specs["cpu"]["cores"] == 20
    assert exact_laptop.specs["cpu"]["tdp_w"] == 55.0
    # Regional OS "FreeDOS" & MPN preserved
    assert exact_laptop.specs["operating_system"]["name"] == "FreeDOS"
    assert exact_laptop.mpn == "83F0006ELK"
    # Noisy store display panel "IPS" overwritten with Icecat's "OLED"
    assert exact_laptop.specs["display"]["panel_type"] == "OLED"
    assert exact_laptop.specs["power_battery"]["power_adapter_w"] == 245.0
    assert exact_laptop.specs["identity"]["color"] == "Eclipse Black"

    # 2. Test VARIANT_MATCH: Store has 16GB RAM & 1024GB SSD (while Icecat has 32GB & 512GB)
    variant_laptop = CanonicalLaptop(
        canonical_id="laptop_lenovo_legion_variant",
        brand="Lenovo",
        laptop_family="Legion",
        laptop_model="Legion 5 15IAX10",
        title="Lenovo Legion 5 15IAX10 16GB 1TB",
        specs={
            "identity": {"brand": "Lenovo", "color": "Storm Grey"},
            "cpu": {"manufacturer": "Intel", "model": "Core Ultra 7 255HX", "cores": 20},
            "gpu": {"manufacturer": "NVIDIA", "model": "GeForce RTX 5060", "vram_gb": 8, "integrated": False},
            "memory": {"capacity_gb": 16, "slot_count": None},
            "storage": {"capacity_gb": 1024, "form_factor": None},
            "display": {"size_inches": 15.1, "refresh_rate_hz": 144},
            "operating_system": {"name": "FreeDOS"},
        },
    )

    IcecatCatalogEnricher.apply_icecat_specs_to_laptop(variant_laptop, icecat_specs, "VARIANT_MATCH")
    # Store RAM (16GB) & Storage (1024GB) & Color ("Storm Grey") strictly preserved!
    assert variant_laptop.specs["memory"]["capacity_gb"] == 16
    assert variant_laptop.specs["storage"]["capacity_gb"] == 1024
    assert variant_laptop.specs["identity"]["color"] == "Storm Grey"
    # Chassis sub-fields & power/physical populated from Icecat!
    assert variant_laptop.specs["memory"]["slot_count"] == 2
    assert variant_laptop.specs["storage"]["form_factor"] == "M.2"
    assert variant_laptop.specs["power_battery"]["battery_capacity_wh"] == 80.0
    assert variant_laptop.specs["power_battery"]["power_adapter_w"] == 245.0
    assert variant_laptop.specs["physical"]["weight_kg"] == 1.9


def test_core_only_ai_envelope_scoping() -> None:
    """Verify core_only_ai=True only generates envelopes for core matching & regional components."""
    pipeline = LaptopExtractionPipeline(ai_fallback=None, core_only_ai=True)
    raw_prod = RawScrapedProduct(
        url="https://example.com/laptop",
        store="compumarts",
        title="Lenovo LOQ 15IRX9 Core i7-13650HX RTX 4050 6GB 16GB RAM 512GB SSD 15.6 144Hz FreeDOS",
        raw_html="",
        raw_tables={"specs": {"Processor": "i7-13650HX", "Battery": "60Wh", "Weight": "2.4kg"}},
        raw_sections={"Description": "Gaming laptop"},
        price=45000.0,
    )
    res = pipeline.process_raw_product(raw_prod)
    generated_components = {env.component_name for env in res.component_envelopes_generated}
    # Deep chassis components must never be generated when core_only_ai=True
    for deep_comp in ("power_battery", "physical", "connectivity", "audio_webcam", "build_security"):
        assert deep_comp not in generated_components
