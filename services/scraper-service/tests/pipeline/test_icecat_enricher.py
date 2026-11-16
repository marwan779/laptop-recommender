"""Unit tests for Icecat Search, OpenIcecat JSON API Parser, and Catalog Enricher."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from app.matching.models import CanonicalLaptop, StoreOffer, UnifiedCatalog
from app.pipeline.icecat.api_service import IcecatAPIService
from app.pipeline.icecat.enricher import IcecatCatalogEnricher
from app.pipeline.icecat.search_service import (
    build_search_queries,
    evaluate_spec_match,
    extract_clean_family,
    extract_core_cpu_chip,
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
    assert parsed["storage"]["interface"] == "PCIe 4.0 NVMe"
    assert parsed["storage"]["form_factor"] == "M.2"
    assert parsed["storage"].get("slot_count") is None
    assert parsed["storage"]["installed_ssd_count"] == 1

    assert parsed["display"]["size_inches"] == 15.1
    assert parsed["display"]["resolution"] == "2560x1600"
    assert parsed["display"]["resolution_width"] == 2560
    assert parsed["display"]["resolution_height"] == 1600
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


def test_not_found_laptop_injects_online_reference_specs() -> None:
    """Verify _build_auditor_record attaches Scrapling online specs to source_table['Online_Reference_Specs']."""
    lap = CanonicalLaptop(
        canonical_id="laptop_lenovo_loq_15irx10",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX10",
        title="Lenovo LOQ 15IRX10 Core i7-13650HX RTX 5050",
        specs={"power_battery": {"battery_capacity_wh": None}},
        raw_store_context={"source_table": {"Processor": "i7-13650HX"}},
    )
    rec = IcecatCatalogEnricher._build_auditor_record(
        lap,
        online_specs="[Source: nanoreview.net]\nBattery: 60 Wh\nWeight: 2.4 kg",
    )
    assert "Online_Reference_Specs" in rec["source_table"]
    assert "Battery: 60 Wh" in rec["source_table"]["Online_Reference_Specs"]


def test_parse_asus_tuf_a16_extended_icecat_fields() -> None:
    """Verify all extended Icecat features (Design, Memory Channels, PCIe Gen, Display Sync, USB-C PD/DP, Copilot, Security) map accurately."""
    tuf_json = {
        "FeaturesGroups": [
            {
                "Features": [
                    {
                        "Feature": {"Name": {"Value": "Colour name"}},
                        "PresentationValue": "Jaeger Gray",
                        "RawValue": "Jaeger Gray",
                    },
                    {
                        "Feature": {"Name": {"Value": "Product colour"}},
                        "PresentationValue": "Black, Grey",
                        "RawValue": "Black, Grey",
                    },
                    {
                        "Feature": {"Name": {"Value": "Form factor"}},
                        "PresentationValue": "Clamshell",
                        "RawValue": "Clamshell",
                    },
                    {
                        "Feature": {"Name": {"Value": "Market positioning"}},
                        "PresentationValue": "Gaming",
                        "RawValue": "Gaming",
                    },
                    {
                        "Feature": {"Name": {"Value": "Introduction year"}},
                        "PresentationValue": "2025",
                        "RawValue": "2025",
                    },
                    {
                        "Feature": {"Name": {"Value": "Display diagonal"}},
                        "PresentationValue": '40.6 cm (16")',
                        "RawValue": "16",
                    },
                    {
                        "Feature": {"Name": {"Value": "Display resolution"}},
                        "PresentationValue": "1920 x 1200 pixels",
                        "RawValue": "1920 x 1200",
                    },
                    {"Feature": {"Name": {"Value": "HD type"}}, "PresentationValue": "WUXGA", "RawValue": "WUXGA"},
                    {"Feature": {"Name": {"Value": "Anti-glare screen"}}, "PresentationValue": "Y", "RawValue": "Y"},
                    {"Feature": {"Name": {"Value": "NVIDIA G-SYNC"}}, "PresentationValue": "Y", "RawValue": "Y"},
                    {
                        "Feature": {"Name": {"Value": "On-board graphics card model"}},
                        "PresentationValue": "AMD Radeon 610M",
                        "RawValue": "AMD Radeon 610M",
                    },
                    {
                        "Feature": {"Name": {"Value": "Memory form factor"}},
                        "PresentationValue": "SO-DIMM",
                        "RawValue": "SO-DIMM",
                    },
                    {
                        "Feature": {"Name": {"Value": "Memory channels"}},
                        "PresentationValue": "Dual-channel",
                        "RawValue": "Dual-channel",
                    },
                    {
                        "Feature": {"Name": {"Value": "SSD interface"}},
                        "PresentationValue": "PCI Express 4.0",
                        "RawValue": "PCI Express 4.0",
                    },
                    {"Feature": {"Name": {"Value": "NVMe"}}, "PresentationValue": "Y", "RawValue": "Y"},
                    {
                        "Feature": {"Name": {"Value": "Number of SSDs installed"}},
                        "PresentationValue": "1",
                        "RawValue": "1",
                    },
                    {
                        "Feature": {"Name": {"Value": "Audio system"}},
                        "PresentationValue": "Dolby Atmos",
                        "RawValue": "Dolby Atmos",
                    },
                    {"Feature": {"Name": {"Value": "Antenna type"}}, "PresentationValue": "2x2", "RawValue": "2x2"},
                    {
                        "Feature": {"Name": {"Value": "Ethernet LAN data rates"}},
                        "PresentationValue": "10, 100, 1000 Mbit/s",
                        "RawValue": "10, 100, 1000",
                    },
                    {
                        "Feature": {"Name": {"Value": "USB Type-C DisplayPort Alternate Mode"}},
                        "PresentationValue": "Y",
                        "RawValue": "Y",
                    },
                    {
                        "Feature": {"Name": {"Value": "USB Power Delivery (USB PD)"}},
                        "PresentationValue": "Y",
                        "RawValue": "Y",
                    },
                    {
                        "Feature": {"Name": {"Value": "USB Type-C charging port"}},
                        "PresentationValue": "Y",
                        "RawValue": "Y",
                    },
                    {"Feature": {"Name": {"Value": "Copilot key"}}, "PresentationValue": "Y", "RawValue": "Y"},
                    {
                        "Feature": {"Name": {"Value": "Battery technology"}},
                        "PresentationValue": "Lithium-Ion (Li-Ion)",
                        "RawValue": "Lithium-Ion (Li-Ion)",
                    },
                    {
                        "Feature": {"Name": {"Value": "Fast charging time (50%)"}},
                        "PresentationValue": "30 min",
                        "RawValue": "30",
                    },
                    {"Feature": {"Name": {"Value": "Face recognition"}}, "PresentationValue": "Y", "RawValue": "Y"},
                    {"Feature": {"Name": {"Value": "Windows Hello"}}, "PresentationValue": "Y", "RawValue": "Y"},
                    {
                        "Feature": {"Name": {"Value": "Trusted Platform Module (TPM)"}},
                        "PresentationValue": "Y",
                        "RawValue": "Y",
                    },
                    {"Feature": {"Name": {"Value": "Password protection"}}, "PresentationValue": "Y", "RawValue": "Y"},
                    {
                        "Feature": {"Name": {"Value": "Password protection type"}},
                        "PresentationValue": "BIOS, User",
                        "RawValue": "BIOS, User",
                    },
                    {
                        "Feature": {"Name": {"Value": "Height (front)"}},
                        "PresentationValue": "1.79 cm",
                        "RawValue": "1.79",
                    },
                    {
                        "Feature": {"Name": {"Value": "Height (rear)"}},
                        "PresentationValue": "2.73 cm",
                        "RawValue": "2.73",
                    },
                ]
            }
        ]
    }
    api = IcecatAPIService(request_delay=0.0)
    parsed = api.parse_product_json(tuf_json)

    assert parsed["identity"]["color"] == "Jaeger Gray"
    assert parsed["identity"]["base_color"] == "Black, Grey"
    assert parsed["identity"]["form_factor"] == "Clamshell"
    assert parsed["identity"]["market_positioning"] == "Gaming"
    assert parsed["identity"]["release_year"] == 2025

    assert parsed["gpu"]["igpu_model"] == "AMD Radeon 610M"
    assert parsed["memory"]["form_factor"] == "SO-DIMM"
    assert parsed["memory"]["channels"] == "Dual-channel"
    assert parsed["storage"]["interface"] == "PCIe 4.0 NVMe"
    assert parsed["storage"]["installed_ssd_count"] == 1

    assert parsed["display"]["hd_type"] == "WUXGA"
    assert parsed["display"]["surface_treatment"] == "Anti-glare"
    assert parsed["display"]["adaptive_sync"] == "G-SYNC"
    assert parsed["display"]["resolution_width"] == 1920
    assert parsed["display"]["resolution_height"] == 1200

    assert parsed["audio_webcam"]["audio_system"] == "Dolby Atmos"
    assert parsed["connectivity"]["wifi_antenna"] == "2x2"
    assert parsed["connectivity"]["ethernet_speed"] == "1 Gbps"
    assert parsed["connectivity"]["usb_c_displayport"] is True
    assert parsed["connectivity"]["usb_c_power_delivery"] is True

    assert parsed["power_battery"]["battery_type"] == "Lithium-Ion (Li-Ion)"
    assert parsed["power_battery"]["fast_charge_50_mins"] == 30
    assert parsed["power_battery"]["usb_c_pd_charging"] is True

    assert parsed["physical"]["height_front_mm"] == 17.9
    assert parsed["physical"]["height_rear_mm"] == 27.3
    assert parsed["physical"]["height_mm"] == 27.3

    assert parsed["build_security"]["has_copilot_key"] is True
    assert "TPM" in parsed["build_security"]["security_features"]
    assert "Windows Hello" in parsed["build_security"]["security_features"]
    assert "Face Recognition" in parsed["build_security"]["security_features"]
    assert "Password Protection (BIOS, User)" in parsed["build_security"]["security_features"]


def test_search_service_snapdragon_display_panel_ram_vetoes():
    """evaluate_spec_match must reject Snapdragon vs Ryzen, OLED vs IPS, DDR5 vs DDR4, and >0.15\" size mismatches."""
    assert extract_core_cpu_chip("Qualcomm Snapdragon X2E88100") == "X2E88100"
    assert extract_core_cpu_chip("Qualcomm Snapdragon X X1 26 100") == "X1-26-100"
    assert extract_core_cpu_chip("Snapdragon X1-26-101") == "X1-26-101"

    snapdragon_laptop = {
        "brand": "ASUS",
        "laptop_family": "Vivobook S14",
        "specs": {
            "cpu": {"model": "Qualcomm Snapdragon X X1-26-100"},
            "gpu": {"model": "Qualcomm Adreno", "integrated": True},
            "memory": {"capacity_gb": 16, "memory_type": "LPDDR5X"},
            "storage": {"capacity_gb": 512},
            "display": {"size_inches": 14.0, "resolution": "1920x1200", "panel_type": "IPS"},
        },
    }
    wrong_ryzen_candidate = {
        "title": 'ASUS Vivobook S14 OLED 14" 1920x1200 AMD Ryzen 5 7535HS 16GB DDR5 512GB SSD',
        "manufacturer_name": "ASUS",
        "short_summary_description": "",
        "long_summary_description": "",
    }
    status, checks = evaluate_spec_match(snapdragon_laptop, wrong_ryzen_candidate)
    assert status == "NO_MATCH"
    assert checks["cpu"] is False
    assert checks["panel"] is False

    # 15.6" vs 16.0" must fail (> 0.15" tolerance) and DDR5 vs DDR4 must fail
    vivobook_15 = {
        "brand": "ASUS",
        "laptop_family": "Vivobook 15",
        "specs": {
            "cpu": {"model": "Intel Core 3 304"},
            "gpu": {"model": "Intel Graphics", "integrated": True},
            "memory": {"capacity_gb": 8, "memory_type": "DDR5"},
            "storage": {"capacity_gb": 512},
            "display": {"size_inches": 15.6, "resolution": "1920x1080", "panel_type": "IPS"},
        },
    }
    wrong_16_ddr4 = {
        "title": 'ASUS Vivobook 16" WUXGA Core 3 304 8GB DDR4 512GB SSD',
        "manufacturer_name": "ASUS",
        "short_summary_description": "",
        "long_summary_description": "",
    }
    status2, checks2 = evaluate_spec_match(vivobook_15, wrong_16_ddr4)
    assert status2 == "NO_MATCH"
    assert checks2["display_size"] is False
    assert checks2["memory_type"] is False


def test_finalize_laptop_specs_store_wins_and_contradiction_guards():
    """Store truth and contradiction guards must hold across repeated finalize_laptop_specs calls."""
    store_specs = {
        "display": {
            "size_inches": 15.6,
            "resolution": "1920x1080",
            "panel_type": "IPS",
            "refresh_rate_hz": 120,
            "touchscreen": False,
            "raw_spec": "Screen Size: 15.6 inches | Resolution: 1920x1080 | Touchscreen: No",
        },
        "power_battery": {"battery_capacity_wh": 41.0, "power_adapter_w": 45.0},
        "memory": {
            "capacity_gb": 16,
            "memory_type": "LPDDR5X",
            "raw_spec": "16GB LPDDR5X on board",
        },
        "storage": {
            "capacity_gb": 512,
            "storage_type": "SSD",
            "interface": "NVMe",
            "raw_spec": "512GB Nvme GEN 4",
        },
        "connectivity": {
            "wifi": "Wi-Fi 6",
            "ethernet": False,
            "ports": ["1x RJ-45 Ethernet", "2x USB 3.2 Gen 1 Type-A"],
        },
        "physical": {"weight_kg": 1.70, "width_mm": 359.7},
        "build_security": {"has_fingerprint": False},
    }
    contaminated = copy.deepcopy(store_specs)
    contaminated["display"]["touchscreen"] = True
    contaminated["display"]["resolution"] = "2560x1600"
    contaminated["power_battery"]["battery_capacity_wh"] = 54.0
    contaminated["memory"]["memory_type"] = "DDR4"
    contaminated["memory"]["slot_count"] = 1
    contaminated["memory"]["form_factor"] = "SO-DIMM"
    contaminated["memory"]["is_soldered"] = False
    contaminated["storage"]["interface"] = "PCIe 3.0 NVMe"
    contaminated["physical"]["weight_kg"] = 1.95

    laptop = CanonicalLaptop(
        canonical_id="test_contradiction_guards",
        title="ASUS Vivobook 15 - FingerPrint",
        brand="ASUS",
        laptop_family="Vivobook",
        laptop_model="15",
        specs=contaminated,
        raw_store_context={
            "store_specs": copy.deepcopy(store_specs),
            "source_table": {"Finger print": "FingerPrint"},
        },
        offers=[],
    )

    IcecatCatalogEnricher.finalize_laptop_specs(laptop)
    # Run twice to confirm multi-pass store_specs is still intact during finalize passes
    IcecatCatalogEnricher.finalize_laptop_specs(laptop)

    assert laptop.specs["display"]["resolution"] == "1920x1080"
    assert laptop.specs["display"]["touchscreen"] is False
    assert laptop.specs["power_battery"]["battery_capacity_wh"] == 41.0
    assert laptop.specs["power_battery"]["power_adapter_w"] == 45.0
    assert laptop.specs["memory"]["memory_type"] == "LPDDR5X"
    assert laptop.specs["memory"]["is_soldered"] is True
    assert laptop.specs["memory"]["form_factor"] == "On-board"
    assert laptop.specs["memory"]["slot_count"] == 0
    assert laptop.specs["storage"]["interface"] == "PCIe 4.0 NVMe"
    assert laptop.specs["connectivity"]["ethernet"] is True
    assert laptop.specs["connectivity"]["ethernet_speed"] == "1 Gbps"
    assert laptop.specs["build_security"]["has_fingerprint"] is True
    assert laptop.specs["physical"]["weight_kg"] == 1.70

    # Negative guards: "Fingerprint: No" and "16GB DDR5 | Memory Slots: One DDR5 slot" must NOT be mangled
    neg_lap = CanonicalLaptop(
        canonical_id="test_negative_guards",
        title="Lenovo IdeaPad Slim 3",
        brand="Lenovo",
        laptop_family="IdeaPad Slim",
        laptop_model="3",
        specs={
            "memory": {
                "capacity_gb": 16,
                "memory_type": "DDR5",
                "slot_count": 1,
                "is_soldered": False,
                "raw_spec": "16GB DDR5 4800Hz",
            },
            "build_security": {"has_fingerprint": False, "raw_spec": "Fingerprint: No"},
        },
        raw_store_context={
            "source_table": {"Memory": "16GB DDR5 4800Hz", "Memory Slots": "One DDR5 slot", "Fingerprint": "No"}
        },
        offers=[],
    )
    IcecatCatalogEnricher.finalize_laptop_specs(neg_lap)
    assert neg_lap.specs["build_security"]["has_fingerprint"] is False
    assert neg_lap.specs["memory"]["slot_count"] == 1
    assert neg_lap.specs["memory"]["is_soldered"] is False


def test_deterministic_extractor_whr_nvme_gen4_and_finger_print():
    """DeterministicExtractor handles '41Whr', 'Nvme GEN 4', and 'Finger print' table keys."""
    from app.pipeline.deterministic import DeterministicExtractor

    ext = DeterministicExtractor()
    specs, _ = ext.extract(
        "ASUS Vivobook 15-X1504VA-BQC857W",
        {
            "Battery": "Integrated 41Whr Battery",
            "Storage": "512GB Nvme GEN 4",
            "Finger print": "FingerPrint",
        },
        {},
    )
    assert specs["power_battery"]["battery_capacity_wh"] == 41.0
    assert specs["storage"]["interface"] == "PCIe 4.0 NVMe"
    assert specs["build_security"]["has_fingerprint"] is True
