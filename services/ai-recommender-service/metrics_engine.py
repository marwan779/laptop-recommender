#!/usr/bin/env python3
"""
Production Hardware Metrics Engine (metrics_engine.py)
Derives all 8 Hardware & Ergonomics Metrics + Flat TOPSIS Input Vector for the 295-laptop catalog.
"""
import json
import math
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Reference Benchmark Scores (Normalized 0-100 scale across mobile silicon)
CPU_BENCHMARK_MAP: Dict[str, float] = {
    # Ultra-High-End 2025/2026 HX & Strix Halo
    "Core Ultra 9 285HX": 99.0,
    "Ryzen 9 9955HX": 98.5,
    "Core Ultra 9 275HX": 97.0,
    "Ryzen AI Max+ 395": 96.5,
    "Core i9-14900HX": 94.0,
    "Ryzen 9 8940HX": 92.5,
    "Core Ultra 7 255HX": 91.0,
    "Core i7-14700HX": 90.0,
    "Ryzen AI 9 HX 370": 88.5,
    "Core i7-14650HX": 86.5,
    "Core i7-13700HX": 85.0,
    "Core i7-13650HX": 84.0,
    "Ryzen 7 8745HX": 83.5,
    "Core i9-13900H": 83.0,
    "Core Ultra 9 285H": 84.5,
    "Core Ultra X9 378H": 85.0,
    "Core Ultra 9 386H": 84.0,
    "Core i7-13645HX": 82.0,
    "Core Ultra 9 185H": 81.0,
    "Core Ultra 7 255H": 80.5,
    "Core Ultra 7 356H": 81.0,
    "Core 9 270H": 79.5,
    "Ryzen AI 7 350": 79.0,
    "Ryzen 7 8845HS": 78.5,
    "Ryzen 7 260": 78.0,
    "Core i7-13700H": 77.5,
    "Core i5-14450HX": 76.5,
    "Core i5-13450HX": 75.5,
    "Core Ultra 7 155H": 76.0,
    "Core 7 240H": 75.0,
    "Core i7-13620H": 74.5,
    "Ryzen 7 250": 74.0,
    "Core Ultra 5 225H": 74.0,
    "Core i7-12700H": 73.0,
    "Core i5-13500H": 72.0,
    "Ryzen 7 170": 71.0,
    "CoreUltra 7 258V": 72.5,
    "Core Ultra 7 258V": 72.5,
    "Core Ultra 7 256V": 72.0,
    "Core Ultra 7 355": 71.5,
    "Core 7 350": 71.0,
    "Core 5 210H": 69.5,
    "Core i5-13420H": 68.5,
    "Core 5 205H": 67.5,
    "Core i5-12450HX": 67.0,
    "Core i7-11800H": 66.5,
    "Ryzen 7 7445HS": 66.0,
    "Ryzen 7 5800H": 65.0,
    "Core Ultra 5 125H": 68.0,
    "Snapdragon X X1-26-100": 67.0,
    "Core Ultra 5 226V": 66.5,
    "Ryzen AI 5 330": 65.5,
    "Core Ultra 7 255U": 65.0,
    "Core Ultra 5 325": 64.5,
    "Core Ultra 5 322": 63.5,
    "Core Ultra 7 155U": 63.0,
    "Core 7 150U": 62.5,
    "Core Ultra 5 235U": 62.0,
    "Core Ultra 5 225U": 61.5,
    "Core i7-1355U": 61.0,
    "Core Ultra 5 125U": 60.5,
    "Ryzen 5 7535U": 60.0,
    "Ryzen 5 7235HS": 59.0,
    "Core 5 120U": 59.0,
    "Ryzen 5 150": 58.0,
    "Core i5-1335U": 57.5,
    "Core i5-1334U": 57.0,
    "Ryzen 5 40": 54.0,
    "Core i7-1165G7": 52.0,
    "Core i5-1135G7": 49.0,
    "Core i3-1315U": 48.0,
    "Core i3-1305U": 45.0,
    "Core i3-1215U": 46.0,
    "Core i3-1005G1": 35.0,
    "Ryzen 3 3250U": 32.0,
    "Athlon Silver 3050U": 25.0,
    "Celeron N3350": 15.0,
}

# GPU Reference: (base_score_at_full_tgp, reference_full_tgp_w)
GPU_BENCHMARK_MAP: Dict[str, tuple] = {
    "GeForce RTX 5090": (100.0, 175.0),
    "GeForce RTX 4090": (93.0, 175.0),
    "GeForce RTX 5080": (89.0, 175.0),
    "GeForce RTX 4080": (83.0, 175.0),
    "GeForce RTX 5070 Ti": (79.0, 140.0),
    "GeForce RTX 5070": (71.0, 115.0),
    "GeForce RTX 4070": (66.0, 115.0),
    "GeForce RTX 5060": (63.0, 115.0),
    "AMD Radeon 8060S": (61.0, 0.0),  # Strix Halo 40-CU integrated beast
    "GeForce RTX 4060": (57.0, 115.0),
    "GeForce RTX 5050": (54.0, 100.0),
    "GeForce RTX 4050": (48.0, 105.0),
    "GeForce RTX 3060": (45.0, 115.0),
    "GeForce RTX 3050": (37.0, 80.0),
    "GeForce RTX 2050": (30.0, 65.0),
    "Intel Arc B390 GPU": (33.0, 0.0),
    "Intel Arc 140V": (29.0, 0.0),
    "Intel Arc 140T": (28.5, 0.0),
    "AMD Radeon 780M": (27.5, 0.0),
    "Intel Arc 130V": (26.0, 0.0),
    "Intel Arc 130T": (25.5, 0.0),
    "Intel Arc Graphics (8 Xe-cores)": (25.0, 0.0),
    "Intel Arc graphics (7 Xe-cores)": (23.5, 0.0),
    "Intel Arc Graphics": (24.0, 0.0),
    "Qualcomm Adreno X1-45": (22.0, 0.0),
    "AMD Radeon 660M": (20.5, 0.0),
    "GeForce MX350": (19.5, 25.0),
    "GeForce MX330": (17.5, 25.0),
    "AMD Radeon 820M (2 graphics cores)": (17.0, 0.0),
    "Intel Graphics (96 execution units)": (18.5, 0.0),
    "Intel Graphics (96 EUs, up to 1.55 GHz)": (18.5, 0.0),
    "Intel Iris Xe Graphics": (18.0, 0.0),
    "Intel Graphics (80 EUs; maximum dynamic frequency 1.3 GHz)": (16.5, 0.0),
    "Intel Graphics (4 Xe-cores; max dynamic frequency 1.95 GHz)": (16.5, 0.0),
    "Intel Graphics (4 Xe-cores)": (16.0, 0.0),
    "Intel UHD Graphics": (13.5, 0.0),
    "AMD Radeon 610M": (12.5, 0.0),
    "AMD Radeon Graphics (3 graphics cores; 1200 MHz)": (12.0, 0.0),
    "AMD Radeon Vega 3 Graphics": (10.5, 0.0),
    "Intel HD Graphics": (7.0, 0.0),
}

LEGACY_ARCHIVED_IDS = {
    "laptop_hp_255_255g8",
    "laptop_hp_2e9j0ea_2e9j0ea",
    "laptop_dell_3510_dell_base_i5_1135g7_mx350_2gb_4gb_1024gb",
    "laptop_lenovo_ideapad_gaming_3_ideapadgaming3",
    "laptop_dell_g15_g155511",
    "laptop_gigabyte_gaming_a16_a16ga6h",
}


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, float(val))), 2)


def compute_laptop_metrics(laptop: Dict[str, Any]) -> Dict[str, Any]:
    specs = laptop["specs"]
    cpu = specs.get("cpu", {})
    gpu = specs.get("gpu", {})
    mem = specs.get("memory", {})
    sto = specs.get("storage", {})
    disp = specs.get("display", {})
    pwr = specs.get("power_battery", {})
    phys = specs.get("physical", {})
    sec = specs.get("build_security", {})
    aud = specs.get("audio_webcam", {})
    conn = specs.get("connectivity", {})
    ident = specs.get("identity", {})
    source_table = laptop.get("raw_store_context", {}).get("source_table", {})
    raw_all_text = (
        str(disp.get("raw_spec") or "") + " " +
        str(gpu.get("raw_spec") or "") + " " +
        str(conn.get("raw_spec") or "") + " " +
        json.dumps(source_table, ensure_ascii=False)
    ).lower()

    # =========================================================================
    # METRIC 1: SILICON PERFORMANCE (CPU & GPU + RAM Bandwidth + AI Readiness)
    # =========================================================================
    cpu_model = cpu.get("model") or ""
    base_cpu_score = CPU_BENCHMARK_MAP.get(cpu_model)
    if base_cpu_score is None:
        # Formula fallback if a new CPU model appears in the future
        cores = float(cpu.get("cores") or 8)
        threads = float(cpu.get("threads") or 12)
        boost = float(cpu.get("clock_boost_ghz") or 4.5)
        cache = float(cpu.get("cache_mb") or 16)
        base_cpu_score = _clamp(cores * 2.5 + threads * 0.8 + (boost - 3.0) * 8.0 + cache * 0.35, 15.0, 98.0)

    # Check Dual-Channel & High-Speed Memory Bandwidth Multiplier
    mem_type = str(mem.get("memory_type") or "DDR5").upper()
    mem_layout = str(mem.get("layout") or "").lower()
    mem_channels = str(mem.get("channels") or "").lower()
    m_spd = re.search(r"(\d{4})", str(mem.get("speed") or ""))
    mem_speed_mhz = int(m_spd.group(1)) if m_spd else (6400 if "LPDDR5" in mem_type else (5200 if "DDR5" in mem_type else 3200))

    is_dual_channel = (
        "dual" in mem_channels or
        mem_layout.startswith("2 x") or
        "LPDDR5" in mem_type or
        "dual-channel" in str(mem.get("raw_spec") or "").lower() or
        (int(mem.get("capacity_gb") or 16) >= 32)
    )
    ram_bw_mult = 1.05 if (is_dual_channel and mem_speed_mhz >= 5200) else (1.02 if is_dual_channel else 1.0)
    effective_cpu_score = _clamp(base_cpu_score * ram_bw_mult, 10.0, 100.0)

    # GPU Scoring
    gpu_model = gpu.get("model") or "Intel UHD Graphics"
    is_igpu = bool(gpu.get("integrated", True))
    gpu_ref_score, gpu_ref_tgp = GPU_BENCHMARK_MAP.get(gpu_model, (18.0 if is_igpu else 45.0, 0.0 if is_igpu else 95.0))
    actual_tgp = float(gpu.get("tdp_w") or 0.0)

    if is_igpu or gpu_ref_tgp <= 0:
        scale_factor_gpu = round(ram_bw_mult, 3)
        effective_gpu_score = _clamp(gpu_ref_score * scale_factor_gpu, 5.0, 100.0)
        tgp_source = "INTEGRATED_SOC"
    else:
        ratio = max(0.4, min(1.35, actual_tgp / gpu_ref_tgp))
        scale_factor_gpu = round(max(0.72, min(1.10, ratio ** 0.32)), 3)
        vram_bonus = 2.5 if str(gpu.get("vram_type") or "").upper() == "GDDR7" else 0.0
        effective_gpu_score = _clamp(gpu_ref_score * scale_factor_gpu + vram_bonus, 15.0, 100.0)
        tgp_source = "EXPLICIT_OR_CHASSIS_CAPPED"

    npu_tops = float(cpu.get("npu_tops") or 0.0)
    gpu_ai_tops = float(gpu.get("ai_tops") or 0.0)
    total_ai_tops = round(npu_tops + gpu_ai_tops, 1)
    is_copilot_plus_pc = bool(npu_tops >= 40.0)

    # Combined silicon index (for general reference; TOPSIS uses both cpu_score and gpu_score directly)
    silicon_index = _clamp(0.45 * effective_cpu_score + 0.55 * effective_gpu_score)

    # =========================================================================
    # METRIC 2: ELECTRICAL POWER SUFFICIENCY MARGIN (Dynamic-Boost Aware)
    # =========================================================================
    adapter_w = float(pwr.get("power_adapter_w") or (65.0 if is_igpu else 170.0))
    cpu_base_w = float(cpu.get("base_power_w") or 28.0)

    if is_igpu:
        board_overhead_w = 15.0
        shared_dynamic_boost_w = 0.0
    else:
        board_overhead_w = 25.0
        # NVIDIA Dynamic Boost / SmartShift shares 15W-20W between CPU & GPU under simultaneous gaming load
        if actual_tgp >= 95.0:
            shared_dynamic_boost_w = 20.0 if cpu_base_w >= 55.0 else 15.0
        elif actual_tgp >= 65.0:
            shared_dynamic_boost_w = 15.0 if cpu_base_w >= 55.0 else 10.0
        else:
            shared_dynamic_boost_w = 5.0

    simultaneous_load_w = cpu_base_w + actual_tgp + board_overhead_w - shared_dynamic_boost_w
    delta_p_watts = round(adapter_w - simultaneous_load_w, 1)

    if delta_p_watts >= 15.0:
        electrical_status = "UNCONSTRAINED_HEADROOM"
        power_score = _clamp(88.0 + min(12.0, (delta_p_watts - 15.0) * 0.2))
    elif delta_p_watts >= -5.0:
        electrical_status = "UNCONSTRAINED_HEADROOM"
        power_score = _clamp(80.0 + (delta_p_watts + 5.0) * 0.4)
    else:
        electrical_status = "DEFICIT_THROTTLED"
        power_score = _clamp(65.0 + delta_p_watts * 1.2, 30.0, 75.0)

    # =========================================================================
    # METRIC 3: DISPLAY OPTICS & QUALITY INDEX (0 to 100)
    # =========================================================================
    size_in = float(disp.get("size_inches") or 15.6)
    res_w = int(disp.get("resolution_width") or 1920)
    res_h = int(disp.get("resolution_height") or 1080)
    ppi = round(math.hypot(res_w, res_h) / size_in, 1) if size_in > 0 else 141.2

    refresh_hz = int(disp.get("refresh_rate_hz") or (144 if not is_igpu else 60))
    panel_type = str(disp.get("panel_type") or "IPS").upper()
    gamut_str = str(disp.get("color_gamut") or "").lower()
    aspect = str(disp.get("aspect_ratio") or ("16:10" if res_h in [1200, 1600, 1800, 2400] else "16:9"))

    # PPI sub-score (max 25 pts)
    ppi_pts = _clamp((ppi - 110.0) / (280.0 - 110.0) * 25.0, 6.0, 25.0)

    # Refresh rate sub-score (max 20 pts)
    if refresh_hz >= 240: hz_pts = 20.0
    elif refresh_hz >= 165: hz_pts = 17.5
    elif refresh_hz >= 144: hz_pts = 15.0
    elif refresh_hz >= 120: hz_pts = 13.0
    elif refresh_hz >= 90: hz_pts = 10.0
    else: hz_pts = 6.0

    # Color gamut sub-score (max 25 pts)
    if "dci-p3" in gamut_str or "oled" in panel_type.lower() or "mini-led" in panel_type.lower():
        gamut_pts = 25.0
        gamut_tier = "100% DCI-P3 (Cinema / Pro Creator)"
    elif "100% srgb" in gamut_str or "72% ntsc" in gamut_str or res_w >= 2560:
        gamut_pts = 21.0
        gamut_tier = "100% sRGB (Creator / Gaming Ready)"
    elif "62.5%" in gamut_str:
        gamut_pts = 13.0
        gamut_tier = "62.5% sRGB (Standard)"
    else:
        gamut_pts = 10.0
        gamut_tier = "45% NTSC (Basic)"

    # Panel type sub-score (max 15 pts)
    if "OLED" in panel_type or "MINI-LED" in panel_type: panel_pts = 15.0
    elif "IPS" in panel_type: panel_pts = 11.5
    elif "VA" in panel_type: panel_pts = 8.5
    else: panel_pts = 5.0

    # Brightness sub-score with smart fallback (max 10 pts)
    nits = disp.get("brightness_nits")
    if nits is None:
        if "OLED" in panel_type or "MINI-LED" in panel_type: nits_eff = 450
        elif res_w >= 2560 or refresh_hz >= 165: nits_eff = 350
        elif not is_igpu or "100% srgb" in gamut_str: nits_eff = 300
        else: nits_eff = 250
    else:
        nits_eff = int(nits)
    nits_pts = _clamp((nits_eff - 200.0) / (600.0 - 200.0) * 10.0, 2.0, 10.0)

    # Aspect ratio sub-score (max 5 pts)
    aspect_pts = 5.0 if aspect in ["16:10", "3:2"] else 3.0

    # Bonus points for Adaptive Sync, HDR, and Fast Response Time (up to +8 pts, capped at 100)
    has_adaptive_sync = bool(disp.get("adaptive_sync") or "g-sync" in raw_all_text or "freesync" in raw_all_text or "adaptive-sync" in raw_all_text)
    has_hdr = bool(disp.get("hdr") or "dolby vision" in raw_all_text or "displayhdr" in raw_all_text or "OLED" in panel_type)
    resp_ms = disp.get("response_time_ms")
    bonus_disp = (3.5 if has_adaptive_sync else 0.0) + (3.5 if has_hdr else 0.0) + (1.5 if (resp_ms is not None and resp_ms <= 3.0) else 0.0)

    display_score = _clamp(ppi_pts + hz_pts + gamut_pts + panel_pts + nits_pts + aspect_pts + bonus_disp, 15.0, 100.0)

    # =========================================================================
    # METRIC 4: ENDURANCE & PORTABILITY INDEX (Mobility — 0 to 100)
    # =========================================================================
    batt_wh = float(pwr.get("battery_capacity_wh") or (70.0 if not is_igpu else 50.0))
    weight_kg = float(phys.get("weight_kg") or (2.3 if not is_igpu else 1.65))
    h_front = phys.get("height_front_mm")
    h_rear = phys.get("height_rear_mm")
    if h_front is not None and h_rear is not None:
        eff_thickness_mm = round((float(h_front) + float(h_rear)) / 2.0, 1)
    else:
        eff_thickness_mm = float(phys.get("height_mm") or (23.5 if not is_igpu else 18.5))

    # Estimate real-world light/mixed battery hours
    idle_system_w = (6.5 if cpu_base_w <= 28 else (9.5 if cpu_base_w <= 45 else 13.0)) + (1.5 if not is_igpu else 0.0) + (1.0 if res_w >= 2560 else 0.0)
    battery_hours_est = round(batt_wh / idle_system_w, 1)

    batt_pts = _clamp((battery_hours_est - 2.5) / (10.5 - 2.5) * 35.0, 5.0, 35.0)
    weight_pts = _clamp((3.2 - weight_kg) / (3.2 - 1.1) * 35.0, 3.0, 35.0)
    thick_pts = _clamp((30.0 - eff_thickness_mm) / (30.0 - 13.5) * 15.0, 2.0, 15.0)

    has_usb_c_pd = bool(pwr.get("usb_c_pd_charging") or conn.get("usb_c_power_delivery") or "power delivery" in raw_all_text)
    has_fast_charge = bool(pwr.get("fast_charging") is not False and (pwr.get("fast_charging") or pwr.get("fast_charge_50_mins") or batt_wh >= 60.0))
    pd_pts = 10.0 if has_usb_c_pd else 0.0
    fc_pts = 5.0 if has_fast_charge else 0.0

    portability_score = _clamp(batt_pts + weight_pts + thick_pts + pd_pts + fc_pts, 15.0, 100.0)
    if weight_kg <= 1.65 and battery_hours_est >= 6.5:
        portability_tier = "ULTRAPORTABLE"
    elif weight_kg <= 2.45:
        portability_tier = "BALANCED"
    else:
        portability_tier = "DESK_BOUND"

    # =========================================================================
    # METRIC 5: UPGRADEABILITY & HARDWARE LONGEVITY (0 to 100 — Zero Double-Counting)
    # =========================================================================
    is_soldered = bool(mem.get("is_soldered", False))
    ram_slots = int(mem.get("slot_count") if mem.get("slot_count") is not None else (0 if is_soldered else 2))
    ram_cap = int(mem.get("capacity_gb") or 16)
    max_ram = int(mem.get("max_supported_gb") or max(ram_cap, 32 if ram_slots >= 2 else ram_cap))
    ram_upgradeable = bool(ram_slots >= 1 and (not is_soldered or "so-dimm" in str(mem.get("form_factor") or "").lower()))

    # RAM Expansion (45 pts)
    if ram_slots >= 2 and not is_soldered:
        ram_exp_pts = 30.0
    elif ram_upgradeable:
        ram_exp_pts = 20.0
    else:
        ram_exp_pts = 12.0 if ram_cap >= 32 else (6.0 if ram_cap >= 16 else 0.0)

    max_ram_pts = 10.0 if max_ram >= 64 else (7.0 if max_ram >= 32 else (4.0 if max_ram >= 16 else 1.0))
    ddr_gen_pts = 5.0 if "5" in mem_type else 2.0
    ram_total_pts = min(45.0, ram_exp_pts + max_ram_pts + ddr_gen_pts)

    # Storage Expansion (40 pts)
    store_sc = laptop.get("raw_store_context", {}).get("store_slot_count")
    if store_sc == 1 and "one m.2" in (sto.get("raw_spec") or "").lower():
        m2_slots = 1
    else:
        m2_slots = int(sto.get("slot_count") or (2 if not is_igpu else 1))
    m2_slots = min(m2_slots, 3)
    installed_ssds = int(sto.get("installed_ssd_count") or 1)
    free_m2_slots = max(0, m2_slots - installed_ssds)
    sto_iface = str(sto.get("interface") or "PCIe 4.0 NVMe")

    m2_slot_pts = 22.0 if m2_slots >= 2 else 10.0
    free_slot_pts = 10.0 if free_m2_slots >= 1 else 3.0
    pcie_pts = 8.0 if "5.0" in sto_iface else (6.5 if "4.0" in sto_iface else 3.5)
    sto_total_pts = min(40.0, m2_slot_pts + free_slot_pts + pcie_pts)

    # Chassis & Structural Longevity (15 pts)
    chassis_mat = str(sec.get("chassis_material") or "").lower()
    fam_low = str(laptop.get("laptop_family") or "").lower()
    if any(k in chassis_mat for k in ["alumin", "magnesium", "metal", "carbon"]) or any(k in fam_low for k in ["zenbook", "proart", "zephyrus", "aorus", "aero", "legion", "omen", "alienware", "prestige", "thinkpad", "envy"]):
        chassis_pts = 14.0
        chassis_tier = "Metal / Reinforced Alloy"
    elif "abs" in chassis_mat or any(k in fam_low for k in ["tuf", "loq", "victus", "nitro", "katana", "cyborg", "probook", "expertbook", "latitude"]):
        chassis_pts = 10.5
        chassis_tier = "MIL-STD / High-Grade PC-ABS"
    else:
        chassis_pts = 7.5
        chassis_tier = "Standard Polycarbonate"

    upgradeability_score = _clamp(ram_total_pts + sto_total_pts + chassis_pts, 15.0, 100.0)
    if ram_upgradeable and m2_slots >= 2:
        upgradeability_tier = "MAXIMUM_UPGRADEABLE"
    elif ram_upgradeable or m2_slots >= 2:
        upgradeability_tier = "MODERATE_EXPANSION"
    else:
        upgradeability_tier = "LOCKED_APPLIANCE"

    # =========================================================================
    # METRIC 7: WORK / STUDY / CONFERENCING & ERGONOMICS INDEX (0 to 100)
    # =========================================================================
    # Webcam & Privacy (35 pts)
    webcam_res = str(aud.get("webcam_resolution") or ("1080p" if int(ident.get("release_year") or 2025) >= 2025 else "720p"))
    has_ir = bool(aud.get("has_ir_camera") or "windows hello" in str(sec.get("security_features") or "").lower() or "ir camera" in raw_all_text)
    has_shutter = bool(aud.get("has_privacy_shutter") or "shutter" in raw_all_text)

    if "5 mp" in webcam_res.lower() or "9 mp" in webcam_res.lower(): cam_pts = 18.0
    elif "1080" in webcam_res: cam_pts = 14.0
    else: cam_pts = 8.0
    ir_pts = 9.0 if has_ir else 0.0
    shutter_pts = 8.0 if has_shutter else 0.0
    webcam_total_pts = min(35.0, cam_pts + ir_pts + shutter_pts)

    # Keyboard & Input Ergonomics (35 pts)
    has_bl = bool(sec.get("has_backlit_keyboard", True))
    bl_type = str(sec.get("keyboard_backlight_type") or ("Backlit" if has_bl else "None"))
    has_numpad = bool(sec.get("has_numpad") if sec.get("has_numpad") is not None else (size_in >= 15.6))
    has_copilot = bool(sec.get("has_copilot_key") or "copilot" in raw_all_text)
    pt_dev = str(sec.get("pointing_device") or "Touchpad")

    if not has_bl: kb_pts = 5.0
    elif any(k in bl_type.lower() for k in ["per-key", "4-zone", "rgb"]): kb_pts = 18.0
    else: kb_pts = 15.0
    numpad_pts = 7.0 if has_numpad else 3.0
    copilot_pts = 5.0 if has_copilot else 0.0
    pt_pts = 5.0 if any(k in pt_dev.lower() for k in ["numberpad", "dialpad", "ultranav"]) else 3.0
    kb_total_pts = min(35.0, kb_pts + numpad_pts + copilot_pts + pt_pts)

    # Audio & Biometrics (30 pts)
    has_fp = bool(sec.get("has_fingerprint", False))
    spk_cnt = int(aud.get("speaker_count") or 2)
    aud_sys = str(aud.get("audio_system") or "")
    bio_pts = 12.0 if (has_fp or has_ir) else 4.0
    spk_pts = 10.0 if spk_cnt >= 4 else 7.0
    aud_brand_pts = 8.0 if (aud_sys or any(k in raw_all_text for k in ["dolby", "dts", "nahimic", "smart amp", "harman", "b&o"])) else 4.0
    aud_total_pts = min(30.0, bio_pts + spk_pts + aud_brand_pts)

    ergonomics_score = _clamp(webcam_total_pts + kb_total_pts + aud_total_pts, 20.0, 100.0)

    # =========================================================================
    # METRIC 8: CONNECTIVITY & EXTERNAL WORKSTATION INDEX (0 to 100)
    # =========================================================================
    wifi_str = str(conn.get("wifi") or "Wi-Fi 6").upper()
    antenna = str(conn.get("wifi_antenna") or "2x2")
    if "WI-FI 7" in wifi_str: wifi_pts = 20.0
    elif "6E" in wifi_str: wifi_pts = 17.0
    elif "WI-FI 6" in wifi_str: wifi_pts = 14.0
    else: wifi_pts = 8.0
    ant_pts = 5.0 if "2x2" in antenna else 2.5

    tb_ver = str(conn.get("thunderbolt_version") or "")
    ports_list = conn.get("ports") or []
    ports_joined = " ".join(ports_list).lower()
    has_usb4 = "usb4" in ports_joined or "usb 4" in raw_all_text
    has_dp = bool(conn.get("usb_c_displayport") or tb_ver or has_usb4 or "displayport" in raw_all_text)

    if "5" in tb_ver: bus_pts = 30.0
    elif "4" in tb_ver or has_usb4: bus_pts = 26.0
    elif has_dp: bus_pts = 20.0
    else: bus_pts = 10.0

    has_lan = bool(conn.get("ethernet") if conn.get("ethernet") is not None else ("rj-45" in ports_joined or "ethernet" in ports_joined or not is_igpu))
    lan_spd = str(conn.get("ethernet_speed") or ("1 Gbps" if has_lan else "None"))
    lan_pts = 15.0 if "2.5" in lan_spd else (12.0 if has_lan else 3.0)
    pd_conn_pts = 10.0 if has_usb_c_pd else 2.0

    # Count total physical ports from ports_list
    total_port_items = 0
    for p_str in ports_list:
        m_cnt = re.match(r"^\s*(\d+)\s*x", str(p_str), re.I)
        total_port_items += int(m_cnt.group(1)) if m_cnt else 1
    if total_port_items == 0:
        total_port_items = 5

    port_cnt_pts = min(13.0, total_port_items * 2.0)
    has_cr = bool(conn.get("has_card_reader") or conn.get("card_reader_type"))
    cr_pts = 7.0 if has_cr else 0.0

    connectivity_score = _clamp(wifi_pts + ant_pts + bus_pts + lan_pts + pd_conn_pts + port_cnt_pts + cr_pts, 20.0, 100.0)

    # =========================================================================
    # METRIC 6: MARKET PRICING & RETAILER ECONOMICS
    # =========================================================================
    cid = laptop["canonical_id"]
    offers = laptop.get("offers", [])
    valid_offers = [o for o in offers if o.get("is_valid_price") and (o.get("price_egp") or 0) >= 5000]
    in_stock_offers = [o for o in valid_offers if o.get("in_stock") is True]

    if cid in LEGACY_ARCHIVED_IDS:
        pricing_status = "LEGACY_ARCHIVED_OUT_OF_STOCK"
        is_Recommendable_Price = False
        eff_price = laptop.get("min_price_egp")
    elif in_stock_offers:
        pricing_status = "IN_STOCK_ACTIVE"
        is_Recommendable_Price = True
        eff_price = min(o["price_egp"] for o in in_stock_offers)
    elif valid_offers:
        pricing_status = "OUT_OF_STOCK_RECENT"
        is_Recommendable_Price = True
        eff_price = min(o["price_egp"] for o in valid_offers)
    else:
        pricing_status = "COMING_SOON_UNPRICED"
        is_Recommendable_Price = False
        eff_price = None

    # Composite Hardware Capability Score for Value-per-EGP computation
    composite_hw = (
        0.28 * effective_cpu_score +
        0.32 * effective_gpu_score +
        0.15 * display_score +
        0.10 * (ram_cap / 32.0 * 100.0 if ram_cap <= 32 else 100.0) +
        0.15 * upgradeability_score
    )
    if eff_price and eff_price >= 10000:
        # Non-linear price-performance index: rewards true sweet-spot hardware per EGP
        value_ratio = round((composite_hw ** 1.35) / (eff_price / 10000.0), 2)
        value_score = _clamp((value_ratio - 18.0) / (58.0 - 18.0) * 100.0, 15.0, 100.0)
    else:
        value_ratio = None
        value_score = 50.0

    # Neutral default for Community NLP Score (75.0) until chassis_reviews_cache.json is attached
    community_nlp_score = 75.0

    return {
        "topsis_inputs": {
            "cpu_score": effective_cpu_score,
            "gpu_score": effective_gpu_score,
            "silicon_index": silicon_index,
            "power_therm_score": power_score,
            "display_score": display_score,
            "mobility_score": portability_score,
            "longevity_score": upgradeability_score,
            "ergonomics_score": ergonomics_score,
            "connectivity_score": connectivity_score,
            "community_nlp_score": community_nlp_score,
            "value_score": value_score,
            "effective_price_egp": eff_price,
            "is_recommendable_price": is_Recommendable_Price,
            "in_stock_active": bool(len(in_stock_offers) > 0 and cid not in LEGACY_ARCHIVED_IDS),
        },
        "silicon": {
            "effective_cpu_score": effective_cpu_score,
            "effective_gpu_score": effective_gpu_score,
            "silicon_index": silicon_index,
            "inferred_tgp_w": actual_tgp,
            "tgp_source": tgp_source,
            "scale_factor_gpu": scale_factor_gpu,
            "ram_bandwidth_multiplier": ram_bw_mult,
            "is_dual_channel": is_dual_channel,
            "total_ai_tops": total_ai_tops,
            "is_copilot_plus_pc": is_copilot_plus_pc,
        },
        "power": {
            "delta_p_watts": delta_p_watts,
            "electrical_status": electrical_status,
            "power_score": power_score,
            "power_adapter_w": adapter_w,
            "simultaneous_load_w": simultaneous_load_w,
        },
        "display": {
            "display_score": display_score,
            "ppi": ppi,
            "refresh_rate_hz": refresh_hz,
            "panel_technology": panel_type,
            "color_gamut_tier": gamut_tier,
            "brightness_nits_effective": nits_eff,
            "aspect_ratio": aspect,
            "has_adaptive_sync": has_adaptive_sync,
            "has_hdr": has_hdr,
        },
        "mobility": {
            "portability_score": portability_score,
            "portability_tier": portability_tier,
            "battery_hours_estimate": battery_hours_est,
            "battery_capacity_wh": batt_wh,
            "weight_kg": weight_kg,
            "effective_thickness_mm": eff_thickness_mm,
            "usb_c_pd_charging": has_usb_c_pd,
            "fast_charging": has_fast_charge,
        },
        "longevity": {
            "upgradeability_score": upgradeability_score,
            "upgradeability_tier": upgradeability_tier,
            "ram_upgradeable": ram_upgradeable,
            "ram_slots": ram_slots,
            "max_ram_gb": max_ram,
            "dual_m2_storage": bool(m2_slots >= 2),
            "total_m2_slots": m2_slots,
            "free_m2_slots": free_m2_slots,
            "pcie_gen": sto_iface,
            "chassis_tier": chassis_tier,
        },
        "ergonomics_and_conferencing": {
            "ergonomics_score": ergonomics_score,
            "webcam_resolution": webcam_res,
            "has_ir_camera": has_ir,
            "has_privacy_shutter": has_shutter,
            "has_backlit_keyboard": has_bl,
            "keyboard_backlight_type": bl_type,
            "has_numpad": has_numpad,
            "has_copilot_key": has_copilot,
            "has_fingerprint": has_fp,
            "speaker_count": spk_cnt,
            "audio_system": aud_sys or "Standard Stereo",
        },
        "connectivity_index": {
            "connectivity_score": connectivity_score,
            "wifi": wifi_str,
            "wifi_antenna": antenna,
            "has_ethernet": has_lan,
            "ethernet_speed": lan_spd,
            "thunderbolt_version": tb_ver or ("USB4" if has_usb4 else None),
            "usb_c_displayport": has_dp,
            "usb_c_power_delivery": has_usb_c_pd,
            "has_card_reader": has_cr,
            "total_ports_count": total_port_items,
        },
        "economics": {
            "min_price_egp": eff_price,
            "cheapest_store": laptop.get("cheapest_store"),
            "max_price_egp": laptop.get("max_price_egp"),
            "price_spread_egp": laptop.get("price_spread_egp"),
            "active_offers_count": len(in_stock_offers),
            "pricing_status": pricing_status,
            "value_ratio": value_ratio,
            "value_score": value_score,
        },
    }


def enrich_catalog_with_metrics(input_path: str, output_path: str) -> Dict[str, Any]:
    with open(input_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    for lap in catalog["laptops"]:
        lap["derived_metrics"] = compute_laptop_metrics(lap)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    return catalog


if __name__ == "__main__":
    in_p = sys.argv[1] if len(sys.argv) > 1 else "unified_catalog_final_v6.json"
    out_p = sys.argv[2] if len(sys.argv) > 2 else "unified_catalog_with_metrics_v6.json"
    cat_out = enrich_catalog_with_metrics(in_p, out_p)
    print(f"Successfully computed derived_metrics for {len(cat_out['laptops'])} laptops -> {out_p}")
