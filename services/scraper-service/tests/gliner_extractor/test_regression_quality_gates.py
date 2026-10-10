import pytest

from gliner_extractor.compumarts_extractor import CompumartsExtractor
from gliner_extractor.hybrid_extractor import HybridLaptopExtractor
from gliner_extractor.token_budget import GLINER_MAX_TOKENS, count_tokens


def test_regression_acer_predator_helios_neo_16():
    """Verify complete spec extraction for Acer Predator Helios Neo 16 AI Gaming Laptop."""
    raw_specs = {
        "Operating System": "Windows 11",
        "Processor": "Intel Core Ultra 9 275HX, 2.70 GHz, 24 Cores / 24 Threads",
        "NPU": "Intel® AI Boost, 13 TOPS",
        "Graphics": "NVIDIA GeForce RTX 5070, 8 GB GDDR7, Boost Clock up to 10 MHz, Max Power 115 W",
        "Display": "16\" Active Matrix TFT LCD, IPS, ComfyView Matte, 2560 × 1600, 240 Hz, 16:10, Non-touch",
        "Memory": "16GB DDR5 SDRAM, microSD card reader",
        "Storage": "1 TB M.2 PCIe NVMe 4.0 SSD",
        "Networking": "Killer Wi-Fi 6E AX1675i (802.11ax), Bluetooth 5.4+, 5 Gigabit Ethernet",
        "Built-in Devices": "Microphone, 2 Speakers, No Fingerprint Reader",
        "Ports & Interfaces": "HDMI ×1, USB 3.2 Gen 1 Type-A ×1, USB 3.2 Gen 2 Type-A ×2, USB 3.2 Gen 2 Type-C ×2, RJ-45, Total USB Ports: 5",
        "Input Devices": "TouchPad, Backlit RGB 4-Zone Keyboard (Predator Sense Key, Copilot Key, Caps Lock Indicator, Mic Mute Indicator)",
        "Battery": "90 Wh Li-Ion, Up to 5 Hours",
        "Power": "230 W Power Supply",
        "Physical Characteristics": "23.90 mm (H) × 356.8 mm (W) × 275.5 mm (D), 2.70 kg, Black",
    }
    title = "Acer Predator Helios Neo 16 AI Gaming Laptop – Ultra 9 275HX, RTX 5070 8GB, 16GB RAM, 1TB SSD, 16\" QHD 240Hz"

    extractor = CompumartsExtractor()
    structured, envelopes = extractor.extract(raw_specs, title)

    # 1. Identity
    assert structured["identity"]["brand"] == "Acer"
    assert "Predator Helios Neo 16" in structured["identity"]["laptop_family"]
    # MPN must never be garbage spec
    assert structured["identity"]["manufacturer_part_number"] != "1TB SSD"

    # 2. CPU
    assert structured["cpu"]["manufacturer"] == "Intel"
    assert structured["cpu"]["model"] == "275HX"
    assert structured["cpu"]["cores"] == 24
    assert structured["cpu"]["threads"] == 24
    assert "2.70" in str(structured["cpu"]["clock_speed"])

    # 3. GPU
    assert structured["gpu"]["manufacturer"] == "NVIDIA"
    assert "RTX 5070" in structured["gpu"]["model"]
    assert structured["gpu"]["vram_gb"] == 8
    assert structured["gpu"]["integrated"] is False

    # 4. Memory
    assert structured["memory"]["capacity_gb"] == 16
    assert structured["memory"]["memory_type"] == "DDR5"

    # 5. Storage
    assert structured["storage"]["capacity_gb"] == 1024
    assert structured["storage"]["storage_type"] == "SSD"
    assert "NVMe" in str(structured["storage"]["interface"])
    assert "M.2" in str(structured["storage"]["form_factor"])

    # 6. Display
    assert structured["display"]["size_inches"] == 16.0
    assert "2560" in str(structured["display"]["resolution"])
    assert "1600" in str(structured["display"]["resolution"])
    assert structured["display"]["refresh_rate_hz"] == 240
    assert structured["display"]["aspect_ratio"] == "16:10"
    assert structured["display"]["panel_type"] == "IPS"
    assert structured["display"]["touchscreen"] is False

    # 7. Power & Battery
    assert structured["power_battery"]["battery_capacity_wh"] == 90.0
    assert structured["power_battery"]["power_adapter_w"] == 230

    # 8. Physical
    assert structured["physical"]["height_mm"] == 23.9
    assert structured["physical"]["width_mm"] == 356.8
    assert structured["physical"]["depth_mm"] == 275.5
    assert structured["physical"]["weight_kg"] == 2.7
    assert structured["physical"]["color"] == "Black"

    # 9. Build & Security
    assert structured["build"]["has_backlit_keyboard"] is True
    assert structured["build"]["has_fingerprint"] is False

    # 10. Audio & Webcam
    assert structured["audio"]["speaker_count"] == 2
    assert "Microphone" in str(structured["audio"]["microphone"])

    # 11. Connectivity
    assert "Wi-Fi 6E" in str(structured["connectivity"]["wifi"]) or "802.11ax" in str(structured["connectivity"]["wifi"])
    assert "5.4" in str(structured["connectivity"]["bluetooth"])
    assert "Gigabit" in str(structured["connectivity"]["ethernet"])
    assert len(structured["connectivity"]["ports"]) > 0

    # 12. OS
    assert "Windows 11" in structured["operating_system"]["name"]


def test_regression_acer_nitro_v_15_dimensions():
    """Verify single-dimension rows Height, Width, Depth on Acer Nitro V 15."""
    raw_specs = {
        "Height": "23.5 mm",
        "Width": "362.3 mm",
        "Depth": "239.9 mm",
        "Weight": "2.11 kg",
        "Color": "Black",
    }
    title = "Acer Nitro V 15 ANV15-52-9340 Gaming Laptop – Core i9-13900H, RTX 5050 8GB GDDR7, 16GB RAM, 512GB NVMe, 15.6\" FHD IPS 165Hz, Black"

    extractor = CompumartsExtractor()
    structured, _ = extractor.extract(raw_specs, title)

    assert structured["physical"]["height_mm"] == 23.5
    assert structured["physical"]["width_mm"] == 362.3
    assert structured["physical"]["depth_mm"] == 239.9
    assert structured["physical"]["weight_kg"] == 2.11
    assert structured["physical"]["color"] == "Black"


def test_token_budget_never_exceeded_on_complex_envelopes():
    """Verify that all envelopes generated strictly stay under GLiNER token limit."""
    raw_specs = {
        "Operating System": "Windows 11 Pro 64-bit National Academic Edition with Microsoft 365 Personal 1-Year Included",
        "Processor": "Intel Core Ultra 9 275HX 24-Core 24-Thread Processor with Intel AI Boost NPU up to 13 TOPS and 30MB Intel Smart Cache",
        "Graphics": "NVIDIA GeForce RTX 5070 Laptop GPU 8GB GDDR7 with ROG Boost at 115W TGP plus 25W Dynamic Boost MUX Switch with NVIDIA Advanced Optimus",
        "Ports & Interfaces": "2x Thunderbolt 4 Type-C (DisplayPort 2.1, Power Delivery 3.0, 40Gbps), 3x USB 3.2 Gen 2 Type-A (10Gbps, 1x Always On), 1x HDMI 2.1 (supports 8K 60Hz or 4K 120Hz), 1x RJ-45 2.5G Gigabit Ethernet, 1x 3.5mm Combo Audio Jack, 1x Full-size SD Express 7.0 Card Reader, 1x DC-in Power Port",
    }
    title = "ASUS ROG Strix SCAR 16 2026 AI Gaming Laptop – Ultra 9 275HX, RTX 5070 8GB, 32GB DDR5 5600MHz, 2TB PCIe 4.0 NVMe M.2 SSD, 16-inch ROG Nebula HDR Display 2.5K 240Hz 3ms Mini LED 1100nits DCI-P3 100%"

    extractor = CompumartsExtractor()
    _, envelopes = extractor.extract(raw_specs, title)

    for env in envelopes:
        prompt_text = env.format_gliner_text()
        tokens = count_tokens(prompt_text, env.target_labels)
        assert tokens <= GLINER_MAX_TOKENS, f"Envelope {env.target_area} exceeded budget: {tokens} tokens > {GLINER_MAX_TOKENS}"
