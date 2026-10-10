"""Unit tests for Phase 1 validators and schema."""

from __future__ import annotations

import pytest
from gliner_extractor.schema import empty_structured
from gliner_extractor.validators import (
    clean_text,
    compute_aspect_ratio,
    normalize_cpu_line,
    normalize_dimensions,
    validate_battery_capacity,
    validate_battery_cells,
    validate_bluetooth,
    validate_brand,
    validate_color,
    validate_cpu_cores_threads,
    validate_display_size,
    validate_ethernet,
    validate_gpu_integrated,
    validate_gpu_vram,
    validate_microphone,
    validate_mpn,
    validate_os_name,
    validate_panel_type,
    validate_power_adapter,
    validate_ram_capacity,
    validate_ram_slots,
    validate_ram_speed,
    validate_ram_type,
    validate_refresh_rate,
    validate_resolution,
    validate_storage_capacity,
    validate_storage_form_factor,
    validate_storage_interface,
    validate_structured,
    validate_webcam,
    validate_weight,
    validate_wifi,
)


def test_empty_structured_schema():
    s = empty_structured()
    assert "identity" in s
    assert "cpu" in s
    assert "gpu" in s
    assert "memory" in s
    assert "storage" in s
    assert "display" in s
    assert "power_battery" in s
    assert "connectivity" in s
    assert "operating_system" in s
    assert "physical" in s
    assert "build" in s
    assert "audio" in s
    assert "webcam" in s
    assert "product_type" in s
    assert "condition" in s
    assert "extraction_meta" in s
    assert s["cpu"]["clock_base_ghz"] is None
    assert s["cpu"]["clock_boost_ghz"] is None
    assert s["gpu"]["secondary_model"] is None


def test_clean_text_noise_and_footnotes():
    raw = "Intel® Core™ Ultra 7 processor\u200e \xa0( 8) 10 11 12 13"
    cleaned = clean_text(raw)
    assert "®" not in cleaned
    assert "™" not in cleaned
    assert "\u200e" not in cleaned
    assert "( 8)" not in cleaned
    assert "10 11 12 13" not in cleaned
    assert "Intel Core Ultra 7 processor" in cleaned


def test_validate_mpn_defect_d1():
    # Defect D1 regressions: junk tokens must be rejected
    bad_mpns = [
        "16GB DDR5",
        "15.6″",
        "15.6\"",
        "1TB",
        "DOS",
        "Mica Silver",
        "Core i7-13620H",
        "14 Cores",
        "83DV",       # Only 4 chars
        "16GB",
        "WUXGA",
        "FHD",
    ]
    for bad in bad_mpns:
        val, err = validate_mpn(bad)
        assert val is None, f"Expected {bad!r} to be rejected, but got {val!r}"
        assert err is not None

    # Valid MPNs (dotted, dashed, hash, alphanumeric)
    good_mpns = [
        "NH.U3PEM.003",
        "90NR0N06-M00F80",
        "B39STAT#A2N",
        "83DV008QED",
        "ANV16-42-R309",
        "FA608PM-RV169W",
    ]
    for good in good_mpns:
        val, err = validate_mpn(good)
        assert val == good, f"Expected {good!r} to pass, got error: {err}"
        assert err is None


def test_validate_ram_speed_defect_d2():
    # Defect D2 regressions: arbitrary numbers must never be accepted as RAM speed
    bad_speeds = [1920, 5060, 5070, 5050, 4050, 2280, 9703, 3407, 6506, 610, 180, 240, 16000]
    for bad in bad_speeds:
        val, err = validate_ram_speed(bad)
        assert val is None, f"Expected speed {bad} to be rejected, got {val}"
        assert err is not None

    # Valid JEDEC speeds
    good_speeds = [3200, 4800, 5200, 5600, 6000, 6400, 7500, 8533]
    for good in good_speeds:
        val, err = validate_ram_speed(good)
        assert val == good
        assert err is None


def test_validate_unvalidated_strings_defect_d3():
    # Wi-Fi
    for bad in ["DDR5", "Ethernet", "USB-A", "MX330", "Type-C", "DOS", "WUXGA", "PCIe"]:
        val, err = validate_wifi(bad)
        assert val is None
    assert validate_wifi("Wi-Fi 6E (802.11ax)")[0] is not None
    assert validate_wifi("Wi-Fi 7")[0] is not None

    # Storage interface
    for bad in ["FreeDOS", "WUXGA", "Intel UHD"]:
        val, err = validate_storage_interface(bad)
        assert val is None
    assert validate_storage_interface("PCIe 4.0 NVMe")[0] is not None
    assert validate_storage_interface("NVMe")[0] is not None

    # Storage form factor
    assert validate_storage_form_factor("DDR5")[0] is None
    assert validate_storage_form_factor("M.2 2280")[0] == "M.2 2280"

    # OS Name
    for bad in ["US MIL-STD 810H", "UEFI", "Shell"]:
        val, err = validate_os_name(bad)
        assert val is None
    assert validate_os_name("Windows 11 Home")[0] == "Windows 11 Home"
    assert validate_os_name("DOS")[0] == "FreeDOS"
    assert validate_os_name("FreeDOS")[0] == "FreeDOS"

    # Webcam resolution
    for bad in ["Microphone", "165Hz", "WQXGA"]:
        val, err = validate_webcam(bad)
        assert val is None
    assert validate_webcam("1080p FHD")[0] is not None

    # Microphone
    for bad in ["HD Webcam", "Dual stereo speakers"]:
        val, err = validate_microphone(bad)
        assert val is None
    assert validate_microphone("Dual array microphone")[0] is not None

    # Color
    for bad in ["45% NTSC", "100% sRGB", "FHD IPS", "Nitro V 15 ANV15-52"]:
        val, err = validate_color(bad, model_name="Nitro V 15 ANV15-52")
        assert val is None
    assert validate_color("Eclipse Black")[0] == "Eclipse Black"
    assert validate_color("Luna Grey")[0] == "Luna Grey"


def test_validate_gpu_vram_and_integrated_defect_d4_d5():
    # D5: iGPUs must have integrated=True
    igpus = ["Intel Arc Graphics", "Radeon Graphics", "Radeon 660M", "Radeon 8060S", "Intel UHD Graphics"]
    for g in igpus:
        is_int, _ = validate_gpu_integrated(g)
        assert is_int is True, f"Expected {g} to be integrated"
        # D4: iGPU VRAM must be None
        vram, err = validate_gpu_vram(16, is_integrated=is_int)
        assert vram is None
        assert err == "integrated_gpu_vram_disallowed"

    # Discrete GPUs
    dgpus = ["GeForce RTX 5060 Laptop GPU", "RTX 4050", "Radeon RX 7600M", "GeForce MX570"]
    for g in dgpus:
        is_int, _ = validate_gpu_integrated(g)
        assert is_int is False, f"Expected {g} to be discrete"
        vram, err = validate_gpu_vram(8, is_integrated=is_int)
        assert vram == 8
        assert err is None


def test_validate_cpu_cores_threads_defect_d6():
    # i3-1315U: 16 cores is impossible
    c, t, err = validate_cpu_cores_threads(16, 8)
    assert err == "cpu_threads_less_than_cores"

    # i5-13420H: 8 cores / 2 threads is invalid (threads < cores)
    c, t, err = validate_cpu_cores_threads(8, 2)
    assert err == "cpu_threads_less_than_cores"

    # Valid cores & threads
    c, t, err = validate_cpu_cores_threads(14, 20)
    assert c == 14 and t == 20 and err is None

    c, t, err = validate_cpu_cores_threads(24, 24)
    assert c == 24 and t == 24 and err is None


def test_normalize_cpu_line_defect_d7():
    assert normalize_cpu_line("Intel® Core™ Ultra 7 processor") == "Core Ultra 7"
    assert normalize_cpu_line("13th Generation Intel Core i7 processor") == "Core i7"
    assert normalize_cpu_line("Core™ 9") == "Core 9"


def test_validate_dimensions_defect_d9():
    # cm to mm conversion (thickness 1.99cm -> 19.9mm, width 36.2cm -> 362mm)
    w, d, h = normalize_dimensions(36.2, 24.0, 1.99)
    assert w == 362.0
    assert d == 240.0
    assert h == 19.9

    # Axis sorting: width >= depth >= height (e.g. H x W x D inverted)
    w, d, h = normalize_dimensions(23.5, 362.3, 239.9)
    assert w == 362.3
    assert d == 239.9
    assert h == 23.5


def test_validate_aspect_ratio_and_resolution_defect_d11_d12():
    # D12: Raw size strings must be rejected
    assert validate_resolution("16 Inches")[0] is None
    assert validate_resolution("15.6-inch")[0] is None

    # Resolution mapping
    res, w, h, _ = validate_resolution("1920 x 1200")
    assert res == "1920 x 1200"
    assert compute_aspect_ratio(w, h) == "16:10"

    res, w, h, _ = validate_resolution("1920 x 1080")
    assert res == "1920 x 1080"
    assert compute_aspect_ratio(w, h) == "16:9"

    res, w, h, _ = validate_resolution("2560 x 1600")
    assert res == "2560 x 1600"
    assert compute_aspect_ratio(w, h) == "16:10"


def test_validate_weight_defect_d21():
    # 6.0 kg and 9.4 kg monitor weights rejected
    assert validate_weight(6.0)[0] is None
    assert validate_weight(9.4)[0] is None

    # Valid laptop weights
    assert validate_weight(2.1)[0] == 2.1
    assert validate_weight("4.63 lb")[0] == 2.1


def test_validate_brand_canonicalization():
    assert validate_brand("asus")[0] == "ASUS"
    assert validate_brand("ROG Strix")[0] == "ASUS"
    assert validate_brand("alienware")[0] == "Dell"
    assert validate_brand("legion")[0] == "Lenovo"
    assert validate_brand("predator")[0] == "Acer"
    assert validate_brand("aorus")[0] == "Gigabyte"


def test_validate_structured_violations():
    record = empty_structured()
    record["identity"]["brand"] = "ASUS"
    record["cpu"]["cores"] = 14
    record["cpu"]["threads"] = 20
    record["gpu"]["vram_gb"] = 8
    record["memory"]["speed"] = 5600
    record["storage"]["capacity_gb"] = 1024
    record["display"]["resolution"] = "1920 x 1200"

    violations = validate_structured(record)
    assert len(violations) == 0

    # Inject invalid RAM speed (D2)
    record["memory"]["speed"] = 5050
    violations = validate_structured(record)
    assert len(violations) == 1
    assert violations[0].field == "memory.speed"
    assert violations[0].rule == "ram_speed_not_in_whitelist"
