"""Regression test suite for the 18 specific pipeline defect repairs.

Verifies:
1. End of support dates (ISO dates like '2031-11-08') rejected from connectivity.ports
2. Clamshell / Classical form factors rejected from build_security.chassis_material
3. sRGB / DCI-P3 color gamuts rejected from display.hdr
4. 157W / CPU PL2 turbo wattages rejected from power_battery.power_adapter_w
5. Stylus disclaimers ('Pen Not Supported') rejected from build_security.pointing_device
6. ASUS marketing recommendation blurbs stripped from operating_system.name
7. Lenovo 4-character machine type (e.g. '83S0') replaced by full 10-char MPN from title/SKU
8. Color technical spec noise ('Gamut', 'Coverage', 'OLED', 'Hz') rejected and duplicates normalized
9. Display resolution (resolution, resolution_width, resolution_height) extracted
10. Display aspect ratio (16:10, 16:9, etc.) extracted and derived
11. Storage interface (PCIe 4.0 NVMe, etc.) extracted and normalized
12. Storage form factor (M.2 2280, M.2 2242, 2.5-inch) extracted
13. Storage slot count (e.g. 'Two M.2 slots', '2x M.2') extracted
14. Storage maximum supported capacity extracted without colliding with installed capacity
15. Memory slot count (e.g. 'Two SO-DIMM slots', 'Single slot', soldered) extracted
16. Memory maximum supported capacity extracted
17. Power battery cells (3-cell, 4-cell, etc.) extracted
18. Power battery fast charging and numpad extracted
"""

import pytest
from app.pipeline.deterministic import DeterministicExtractor
from app.pipeline.sanitizer import TextSanitizer


@pytest.fixture
def extractor() -> DeterministicExtractor:
    return DeterministicExtractor()


@pytest.fixture
def sanitizer() -> TextSanitizer:
    return TextSanitizer()


# 1. End of support date rejected from ports
def test_end_of_support_date_rejected_from_ports(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "End of Support": "2031-11-08",
        "Ports": "2x USB 3.2 Gen 1, 1x HDMI 2.1, 1x Audio combo jack",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo ThinkPad E14",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    ports = specs["connectivity"]["ports"]
    assert ports is not None
    assert not any("2031" in p for p in ports)
    assert not any("End of Support" in p for p in ports)
    assert any("USB" in p for p in ports)


# 2. Clamshell / Classical form factors rejected from chassis_material
def test_clamshell_form_factor_rejected_from_chassis_material(
    extractor: DeterministicExtractor, sanitizer: TextSanitizer
):
    raw_table = {
        "Form Factor": "Clamshell",
        "Case Material": "Aluminium (Top), PC-ABS (Bottom)",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo ThinkPad E14",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    mat = specs["build_security"]["chassis_material"]
    assert mat is not None
    assert "Clamshell" not in mat
    assert "Aluminium" in mat


# 3. Color gamuts rejected from display.hdr
def test_color_gamut_rejected_from_hdr(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Display": "15.6 FHD 144Hz IPS",
        "RGB Colour Space": "100% sRGB",
        "HDR Support": "HDR 400 True Black",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="ASUS Zenbook 15",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["display"]["hdr"] == "HDR 400 True Black"
    assert specs["display"]["color_gamut"] == "100% sRGB"

    # Test negative: purely gamut, no genuine HDR
    raw_table_no_hdr = {
        "Display": "15.6 FHD 144Hz IPS",
        "Color Gamut": "45% NTSC",
    }
    clean_table_no_hdr = sanitizer.sanitize_table(raw_table_no_hdr)
    specs_no_hdr, _ = extractor.extract(
        title="HP Victus 15",
        sanitized_table=clean_table_no_hdr,
        sanitized_sections={},
    )
    assert specs_no_hdr["display"]["hdr"] is None
    assert specs_no_hdr["display"]["color_gamut"] == "45% NTSC"


# 4. CPU Turbo PL2 wattage rejected from power_adapter_w
def test_cpu_turbo_pl2_rejected_from_power_adapter_w(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Processor": "Intel Core i7-14700HX (Base Power 55W, Maximum Turbo Power 157W)",
        "Power Supply": "240W AC Adapter",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo Legion 5",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["power_battery"]["power_adapter_w"] == 240

    # Negative: row with ONLY cpu turbo wattage should NOT set power_adapter_w
    raw_table_turbo_only = {
        "Processor": "Intel Core i7-13650HX up to 157W Turbo",
    }
    clean_table_turbo = sanitizer.sanitize_table(raw_table_turbo_only)
    specs_turbo, _ = extractor.extract(
        title="Gaming Laptop",
        sanitized_table=clean_table_turbo,
        sanitized_sections={},
    )
    assert specs_turbo["power_battery"]["power_adapter_w"] is None


# 5. Stylus disclaimers rejected from pointing_device
def test_stylus_negative_disclaimers_rejected_from_pointing_device(
    extractor: DeterministicExtractor, sanitizer: TextSanitizer
):
    raw_table = {
        "Pen": "Pen Not Supported",
        "Pointing Device": "Buttonless Mylar surface multi-touch touchpad",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo IdeaPad Slim 3",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    pd = specs["build_security"]["pointing_device"]
    assert pd is not None
    assert "Not Supported" not in pd
    assert "touchpad" in pd.lower()


# 6. ASUS marketing recommendation blurbs stripped from operating_system.name
def test_operating_system_marketing_recommendation_blurb_stripped(
    extractor: DeterministicExtractor, sanitizer: TextSanitizer
):
    raw_table = {
        "Operating System": "Windows 11 Home (ASUS recommends Windows 11 Pro for business)",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="ASUS TUF Gaming A15",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["operating_system"]["name"] == "Windows 11 Home"


# 7. Lenovo 4-character machine type replaced by full 10-char MPN from title/SKU
def test_lenovo_4char_machine_type_replaced_by_full_mpn(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Machine Type": "83S0",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    title = "Lenovo LOQ Essential 15ARP10 Gaming Laptop – Model 83S000C2IN"
    specs, _ = extractor.extract(
        title=title,
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["identity"]["manufacturer_part_number"] == "83S000C2IN"


# 8. Color technical spec noise rejected and duplicates normalized
def test_color_noise_filtering_and_deduplication(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Color": "Luna Grey Luna Grey",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo Laptop",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["identity"]["color"] == "Luna Grey"

    # Reject display technical specs from color
    raw_table_bad = {
        "Color": "100% sRGB Coverage OLED",
    }
    clean_table_bad = sanitizer.sanitize_table(raw_table_bad)
    specs_bad, _ = extractor.extract(
        title="ASUS Laptop",
        sanitized_table=clean_table_bad,
        sanitized_sections={},
    )
    assert specs_bad["identity"]["color"] is None


# 9. Display resolution extracted
def test_display_resolution_extraction(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Display": "15.6-inch, FHD (1920 x 1080) 16:9, 144Hz, IPS-level, Anti-glare",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="ASUS TUF",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["display"]["resolution"] == "1920x1080"
    assert specs["display"]["resolution_width"] == 1920
    assert specs["display"]["resolution_height"] == 1080


# 10. Display aspect ratio extracted and derived
def test_display_aspect_ratio_extraction_and_derivation(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Display": "16.0-inch 2560 x 1600 WQXGA IPS 165Hz",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo Legion",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["display"]["aspect_ratio"] == "16:10"
    assert specs["display"]["resolution"] == "2560x1600"


# 11. Storage interface and form factor extracted
def test_storage_interface_and_form_factor_extraction(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Storage": "1TB PCIe 4.0 NVMe M.2 2280 SSD",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Gaming Laptop",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["storage"]["capacity_gb"] == 1024
    assert specs["storage"]["interface"] == "PCIe 4.0 NVMe"
    assert specs["storage"]["form_factor"] == "M.2 2280"


# 12. Storage slot count extracted
def test_storage_slot_count_multi_drive(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Storage": "512GB SSD M.2 2242 PCIe 4.0x4 NVMe",
        "Storage Slot": "Two M.2 slots (one 2280 PCIe 5.0, one 2280 PCIe 4.0)",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="ASUS TUF Gaming",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["storage"]["slot_count"] == 2


# 13. Max storage support isolation
def test_max_storage_support_isolation(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Storage": "512GB SSD M.2 2242 PCIe 4.0x4 NVMe",
        "Max Storage Support": "Up to two drives, 2x M.2 SSD up to 1TB each",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo LOQ 15",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["storage"]["capacity_gb"] == 512
    assert specs["storage"]["max_supported_gb"] == 2048


# 14. Memory slot count and max capacity extracted
def test_memory_slot_count_and_max_capacity(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Memory": "16GB DDR5-5600",
        "Memory Slots": "Two DDR5 SO-DIMM slots, dual-channel capable",
        "Max Memory": "Up to 32GB DDR5-5600",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo Legion 5",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["memory"]["capacity_gb"] == 16
    assert specs["memory"]["slot_count"] == 2
    assert specs["memory"]["max_supported_gb"] == 32
    assert specs["memory"]["is_soldered"] is False


# 15. Memory soldered detection
def test_memory_soldered_detection(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Memory": "16GB Soldered LPDDR5x-7467",
        "Memory Slots": "Memory soldered to systemboard, no slots, dual-channel",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo Slim 7",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["memory"]["capacity_gb"] == 16
    assert specs["memory"]["is_soldered"] is True
    assert specs["memory"]["slot_count"] == 0


# 16. Power battery cells extraction
def test_power_battery_cells_extraction(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Battery": "Integrated 60Wh, 4-cell Li-ion",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo LOQ",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["power_battery"]["battery_capacity_wh"] == 60
    assert specs["power_battery"]["battery_cells"] == 4


# 17. Power battery fast charging extraction
def test_power_battery_fast_charging(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Battery": "Integrated 60Wh, supports Rapid Charge Pro (50% in 30 mins)",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo LOQ",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["power_battery"]["fast_charging"] == "Rapid Charge Pro"


# 18. Numpad extraction
def test_numpad_extraction(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Keyboard": "White Backlit, English (US) with Numeric Keypad",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="Lenovo LOQ",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["build_security"]["has_numpad"] is True
    assert specs["build_security"]["has_backlit_keyboard"] is True


# 19. Bluetooth 6.0 extraction
def test_bluetooth_6_0_extraction(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Wireless": "Wi-Fi 7 (802.11be) Tri-Band + Bluetooth 6.0",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="ASUS ROG Zephyrus Duo 16",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["connectivity"]["bluetooth"] == "Bluetooth 6.0"
    assert specs["connectivity"]["wifi"] == "Wi-Fi 7"


# 20. Additional I/O routing and card reader extraction
def test_additional_io_routing_and_card_reader(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Additional I/O": "1x HDMI 2.1, 1x 3.5mm Combo Audio Jack, 1x microSD UHS-II Card Reader",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="ASUS ROG Zephyrus Duo 16",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["connectivity"]["has_card_reader"] is True
    assert specs["connectivity"]["card_reader_type"] == "MicroSD"
    assert any("HDMI 2.1" in p for p in specs["connectivity"]["ports"])


# 21. Touchscreen extraction
def test_touchscreen_extraction(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    specs, _ = extractor.extract(
        title="ASUS ROG Zephyrus Duo 16 GX651AX Dual 16″ 3K OLED Touch 120Hz",
        sanitized_table={},
        sanitized_sections={},
    )
    assert specs["display"]["touchscreen"] is True


# 22. Hyphenated speaker count extraction
def test_hyphenated_speaker_count(extractor: DeterministicExtractor, sanitizer: TextSanitizer):
    raw_table = {
        "Audio": "4-Speaker System (dual-force woofer) with Smart Amplifier Technology",
    }
    clean_table = sanitizer.sanitize_table(raw_table)
    specs, _ = extractor.extract(
        title="ASUS ROG Zephyrus Duo 16",
        sanitized_table=clean_table,
        sanitized_sections={},
    )
    assert specs["audio_webcam"]["speaker_count"] == 4


# 23. Connectivity component envelope dispatched when fields missing
def test_connectivity_component_envelope_dispatched():
    from app.pipeline.orchestrator import LaptopExtractionPipeline
    from app.pipeline.schema import RawScrapedProduct

    orchestrator = LaptopExtractionPipeline(log_envelopes=False)
    product = RawScrapedProduct(
        url="https://test.com/laptop",
        store="test",
        title="ASUS ROG Zephyrus Duo 16",
        raw_html="<html></html>",
        raw_tables={
            "specs": {
                "Processor": "AMD Ryzen 9 7945HX",
                "Graphics": "RTX 4090 16GB GDDR6",
                "Memory": "32GB DDR5",
                "Storage": "2TB SSD",
                "Display": "16 QHD+ 240Hz",
                "Battery": "90Wh",
                "Weight": "2.6 kg",
                "Networking": "Wi-Fi 7",
            }
        },
        raw_sections={"Connectivity": "Wi-Fi 7, no bluetooth details"},
    )
    result = orchestrator.process_raw_product(product)
    conn_envelopes = [e for e in result.component_envelopes_generated if e.component_name == "connectivity"]
    assert len(conn_envelopes) == 1
    targets = [k for k, v in conn_envelopes[0].sub_schema.items() if v is None]
    assert "bluetooth" in targets
