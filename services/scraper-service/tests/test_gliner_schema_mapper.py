"""Unit tests for LaptopSchemaMapper."""

import pytest
from gliner_extractor.schema_mapper import LaptopSchemaMapper, DEFAULT_LABELS


def test_schema_mapper_empty():
    """Test mapping empty entities returns valid schema structure with nulls."""
    res = LaptopSchemaMapper.map_entities([])
    assert res["identity"]["brand"] is None
    assert res["cpu"]["cores"] is None
    assert res["display"]["touchscreen"] is False
    assert res["raw_entity_count"] == 0


def test_schema_mapper_basic_laptop():
    """Test mapping typical laptop entity spans."""
    entities = [
        {"label": "brand", "text": "Acer", "score": 0.95},
        {"label": "laptop family", "text": "Nitro V 15", "score": 0.90},
        {"label": "laptop model", "text": "ANV15-A31", "score": 0.88},
        {"label": "part number", "text": "ANV15-A31-R8LA", "score": 0.85},
        {"label": "processor manufacturer", "text": "AMD", "score": 0.96},
        {"label": "processor line", "text": "Ryzen 7", "score": 0.94},
        {"label": "processor model", "text": "170", "score": 0.91},
        {"label": "cpu core count", "text": "8 Core", "score": 0.89},
        {"label": "cpu thread count", "text": "16", "score": 0.90},
        {"label": "cpu clock speed", "text": "3.20 GHz", "score": 0.92},
        {"label": "graphics manufacturer", "text": "NVIDIA", "score": 0.97},
        {"label": "graphics model", "text": "GeForce RTX 5060", "score": 0.95},
        {"label": "graphics vram", "text": "8 GB", "score": 0.93},
        {"label": "graphics power wattage", "text": "75 W", "score": 0.87},
        {"label": "ram capacity", "text": "16 GB", "score": 0.96},
        {"label": "ram type", "text": "DDR5 SDRAM", "score": 0.94},
        {"label": "ram speed", "text": "4.80 GT/s", "score": 0.85},
        {"label": "storage capacity", "text": "512 GB", "score": 0.95},
        {"label": "storage type", "text": "SSD", "score": 0.92},
        {"label": "storage interface", "text": "PCI Express NVMe 4.0", "score": 0.88},
        {"label": "screen size", "text": "15.6\"", "score": 0.95},
        {"label": "screen resolution", "text": "1920 x 1080", "score": 0.97},
        {"label": "display panel type", "text": "IPS", "score": 0.90},
        {"label": "display refresh rate", "text": "165 Hz", "score": 0.94},
        {"label": "battery capacity", "text": "57 Wh", "score": 0.89},
        {"label": "power adapter wattage", "text": "135 W", "score": 0.91},
        {"label": "port", "text": "HDMI 2.1", "score": 0.85},
        {"label": "port", "text": "USB Type-C", "score": 0.88},
        {"label": "operating system", "text": "Windows 11 Home", "score": 0.93},
    ]

    res = LaptopSchemaMapper.map_entities(entities)

    # Assert Identity
    assert res["identity"]["brand"] == "Acer"
    assert res["identity"]["laptop_family"] == "Nitro V 15"
    assert res["identity"]["laptop_model"] == "ANV15-A31"
    assert res["identity"]["manufacturer_part_number"] == "ANV15-A31-R8LA"

    # Assert CPU
    assert res["cpu"]["manufacturer"] == "AMD"
    assert res["cpu"]["cores"] == 8
    assert res["cpu"]["threads"] == 16
    assert res["cpu"]["full_name"] == "AMD Ryzen 7 170"

    # Assert GPU
    assert res["gpu"]["manufacturer"] == "NVIDIA"
    assert res["gpu"]["model"] == "GeForce RTX 5060"
    assert res["gpu"]["vram_gb"] == 8
    assert res["gpu"]["tdp_w"] == 75
    assert res["gpu"]["integrated"] is False

    # Assert RAM & Storage
    assert res["memory"]["capacity_gb"] == 16
    assert res["memory"]["memory_type"] == "DDR5 SDRAM"
    assert res["storage"]["capacity_gb"] == 512
    assert res["storage"]["storage_type"] == "SSD"

    # Assert Display
    assert res["display"]["size_inches"] == 15.6
    assert res["display"]["resolution_width"] == 1920
    assert res["display"]["resolution_height"] == 1080
    assert res["display"]["refresh_rate_hz"] == 165
    assert res["display"]["touchscreen"] is False

    # Assert Battery & Ports
    assert res["power_battery"]["battery_capacity_wh"] == 57.0
    assert res["power_battery"]["power_adapter_w"] == 135.0
    assert "HDMI 2.1" in res["connectivity"]["ports"]
    assert "USB Type-C" in res["connectivity"]["ports"]


def test_schema_mapper_storage_tb():
    """Test 1 TB parsing into 1024 GB."""
    entities = [
        {"label": "storage capacity", "text": "1 TB", "score": 0.9},
    ]
    res = LaptopSchemaMapper.map_entities(entities)
    assert res["storage"]["capacity_gb"] == 1024


def test_default_labels_non_empty():
    """Ensure DEFAULT_LABELS contains all required domain labels."""
    assert "brand" in DEFAULT_LABELS
    assert "processor model" in DEFAULT_LABELS
    assert "graphics model" in DEFAULT_LABELS
    assert len(DEFAULT_LABELS) >= 20


def test_direct_key_matcher_fixes():
    """Test DirectKeyMatcher enhancements for sub-brands, RAM, GPU, and Display."""
    from gliner_extractor.key_matcher import DirectKeyMatcher

    matcher = DirectKeyMatcher()

    # 1. Test Memory (RAM) with dual-channel and uncommon modules
    specs_ram = {
        "Memory (RAM)": "24GB DDR5-4800MHz (2x 12GB Dual-Channel Config)",
    }
    struct, _ = matcher.match_specs(specs_ram)
    assert struct["memory"]["capacity_gb"] == 24

    specs_ram_single = {
        "Memory (RAM)": "12GB SO-DIMM DDR5-4800 (Two slots total, Upgradable up to 32GB)",
    }
    struct2, _ = matcher.match_specs(specs_ram_single)
    assert struct2["memory"]["capacity_gb"] == 12

    # 2. Test Storage expansion limit not masking installed capacity
    specs_storage = {
        "Storage": "2x PCIe Gen4x4 M.2 slot; Up to 4TB PCIe NVMe M.2 SSD",
    }
    struct3, _ = matcher.match_specs(specs_storage)
    assert struct3["storage"]["capacity_gb"] is None
    assert struct3["storage"]["max_supported_gb"] == 4096

    # 3. Test Display unicode prime parsing
    assert matcher.parse_inches("13.3″ 3K OLED Touch, 2880 x 1800") == 13.3
    assert matcher.parse_inches("15.6\" FHD") == 15.6

    # 4. Test Dedicated GPU detection
    specs_gpu = {
        "Graphics Card": "NVIDIA GeForce RTX 5090 24GB",
    }
    struct4, _ = matcher.match_specs(specs_gpu)
    assert struct4["gpu"]["model"] == "GeForce RTX 5090"
    assert struct4["gpu"]["manufacturer"] == "NVIDIA"
    assert struct4["gpu"]["vram_gb"] == 24
    assert struct4["gpu"]["integrated"] is False

    # 5. Test Chipset does not clobber processor
    specs_cpu_chipset = {
        "Processor": "13th Gen Intel Core i7-13650HX, 14C (6P + 8E) / 20T",
        "Chipset": "Intel HM770",
    }
    struct5, _ = matcher.match_specs(specs_cpu_chipset)
    assert struct5["cpu"]["full_name"] == "13th Gen Intel Core i7-13650HX, 14C (6P + 8E) / 20T"

    # 6. Test Integrated GPU parsing (including store typo 'Intergrated')
    specs_adreno = {
        "Integrated GPU": "Qualcomm® Adreno® GPU",
    }
    struct6, _ = matcher.match_specs(specs_adreno)
    assert struct6["gpu"]["model"] == "Adreno GPU"
    assert struct6["gpu"]["manufacturer"] == "Qualcomm"
    assert struct6["gpu"]["integrated"] is True

    specs_radeon = {
        "Intergrated GPU": "AMD Radeon® Graphics",
    }
    struct7, _ = matcher.match_specs(specs_radeon)
    assert struct7["gpu"]["model"] == "Radeon Graphics"
    assert struct7["gpu"]["manufacturer"] == "AMD"
    assert struct7["gpu"]["integrated"] is True


def test_compumarts_extractor_modular_methods():
    """Test dedicated CompumartsExtractor modular methods and context envelopes."""
    from gliner_extractor.compumarts_extractor import CompumartsExtractor, ContextEnvelope

    ext = CompumartsExtractor()
    title = "Lenovo Legion 5 15IRX10 Gaming Laptop Intel Core i7-13650HX RTX 5070 32GB DDR5 1TB SSD 15.3 Inch"
    raw_specs = {
        "Processor": "13th Gen Intel Core i7-13650HX, 14C (6P + 8E) / 20T",
        "Chipset": "Intel HM770",
        "Graphics": "NVIDIA GeForce RTX 5070 8GB GDDR7, TGP 115W",
        "Memory (RAM)": "32GB SO-DIMM DDR5-5600 (2x 16GB)",
        "Storage": "1TB SSD M.2 2280 PCIe 4.0x4 NVMe",
        "Display": "15.3\" WUXGA (1920x1200) IPS 165Hz",
        "Operating System": "Windows 11 Home",
        "Battery": "80Wh",
        "Power Adapter": "230W Slim Tip",
        "Weight": "2.25 kg",
        "Ports": "1x USB-C 3.2 Gen 2, 3x USB-A, 1x HDMI 2.1",
    }

    structured, envelopes = ext.extract(raw_specs, title)

    # 1. Identity & Brand
    assert structured["identity"]["brand"] == "Lenovo"
    assert structured["identity"]["laptop_family"] == "Legion 5"

    # 2. CPU (Chipset did not clobber processor)
    assert structured["cpu"]["manufacturer"] == "Intel"
    assert structured["cpu"]["model"] == "13650HX"
    assert structured["cpu"]["line"] == "Core i7"

    # 3. GPU
    assert structured["gpu"]["manufacturer"] == "NVIDIA"
    assert structured["gpu"]["model"] == "GeForce RTX 5070"
    assert structured["gpu"]["vram_gb"] == 8
    assert structured["gpu"]["tdp_w"] == 115

    # 4. RAM
    assert structured["memory"]["capacity_gb"] == 32

    # 5. Storage
    assert structured["storage"]["capacity_gb"] == 1024
    assert structured["storage"]["interface"] == "PCIe 4.0 NVMe"

    # 6. Display
    assert structured["display"]["size_inches"] == 15.3
    assert structured["display"]["resolution"] == "1920 x 1200"
    assert structured["display"]["refresh_rate_hz"] == 165

    # 7. Connectivity & Power
    assert structured["power_battery"]["battery_capacity_wh"] == 80.0
    assert structured["power_battery"]["power_adapter_w"] == 230
    assert len(structured["connectivity"]["ports"]) >= 1

    # 8. Test ContextEnvelope format
    env = ContextEnvelope(
        target_area="memory",
        target_labels=["ram capacity", "ram type"],
        raw_key="Special Memory",
        raw_value="16GB LPDDR5X onboard",
        product_title="ASUS Zenbook S 16",
        sibling_context={"cpu": "Ryzen AI 9"},
    )
    prompt = env.format_gliner_text()
    assert "ASUS Zenbook S 16" in prompt
    assert "Special Memory: 16GB LPDDR5X onboard" in prompt
    assert "Ryzen AI 9" in prompt



