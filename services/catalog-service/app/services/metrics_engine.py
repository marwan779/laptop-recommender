"""Deterministic Hardware Metrics Calculation Engine.

Computes the 6 objective hardware metrics from catalog specifications:
1. Silicon Performance Specs (Effective GPU & Effective CPU with power scaling)
2. Electrical Power Sufficiency Margin (Delta P)
3. Display Optics & Quality Index (0 - 100)
4. Endurance & Portability Index (0 - 100)
5. Upgradeability & Hardware Longevity (0 - 100)
6. Market Pricing & Retailer Economics (Value Ratio)
"""

from __future__ import annotations

from typing import Any


def clamp(val: float, min_val: float, max_val: float) -> float:
    """Clamp value between min_val and max_val."""
    return max(min_val, min(val, max_val))


# -----------------------------------------------------------------------------
# Curated Hardware Baseline Scores (Used when base_score is omitted in JSON)
# -----------------------------------------------------------------------------
DEFAULT_GPU_BASELINES: dict[str, tuple[float, float, float]] = {
    # model_substring: (base_score_raw, tgp_min, tgp_max)
    "rtx 5090": (24000.0, 80.0, 175.0),
    "rtx 5080": (20500.0, 70.0, 175.0),
    "rtx 5070 ti": (15500.0, 60.0, 140.0),
    "rtx 5070": (13500.0, 50.0, 140.0),
    "rtx 5060": (11800.0, 45.0, 140.0),
    "rtx 5050": (9200.0, 40.0, 115.0),
    "rtx 4090": (20000.0, 80.0, 175.0),
    "rtx 4080": (17500.0, 60.0, 175.0),
    "rtx 4070": (12200.0, 35.0, 140.0),
    "rtx 4060": (10500.0, 35.0, 140.0),
    "rtx 4050": (8400.0, 35.0, 115.0),
    "rtx 3080 ti": (13000.0, 80.0, 175.0),
    "rtx 3080": (11500.0, 80.0, 165.0),
    "rtx 3070 ti": (10800.0, 80.0, 150.0),
    "rtx 3070": (9800.0, 60.0, 140.0),
    "rtx 3060": (8200.0, 60.0, 130.0),
    "rtx 3050 ti": (5800.0, 35.0, 80.0),
    "rtx 3050 6gb": (5200.0, 35.0, 75.0),
    "rtx 3050": (4500.0, 35.0, 75.0),
    "rtx 2060": (6200.0, 65.0, 115.0),
    "rtx 2050": (3800.0, 30.0, 55.0),
    "gtx 1660 ti": (5200.0, 60.0, 80.0),
    "gtx 1650 ti": (3600.0, 35.0, 55.0),
    "gtx 1650": (3200.0, 35.0, 50.0),
    "gtx 1050 ti": (2400.0, 40.0, 60.0),
    "gtx 1050": (2000.0, 40.0, 60.0),
    "mx570": (2800.0, 15.0, 30.0),
    "mx550": (2400.0, 15.0, 30.0),
    "mx450": (2100.0, 12.0, 28.0),
    "mx350": (1500.0, 10.0, 25.0),
    "arc 140v": (3400.0, 17.0, 37.0),
    "arc 130v": (2800.0, 17.0, 37.0),
    "arc 140t": (3500.0, 20.0, 45.0),
    "arc b390": (4200.0, 25.0, 50.0),
    "arc graphics": (2900.0, 20.0, 45.0),
    "radeon 890m": (3600.0, 15.0, 54.0),
    "radeon 880m": (3100.0, 15.0, 54.0),
    "radeon 780m": (2900.0, 15.0, 54.0),
    "radeon 760m": (2200.0, 15.0, 35.0),
    "radeon 680m": (2600.0, 15.0, 45.0),
    "radeon 660m": (1800.0, 15.0, 30.0),
    "radeon 820m": (1200.0, 15.0, 28.0),
    "radeon 610m": (900.0, 15.0, 25.0),
    "iris xe": (1500.0, 12.0, 28.0),
    "intel graphics": (1200.0, 12.0, 28.0),
    "uhd graphics": (800.0, 10.0, 25.0),
}

DEFAULT_CPU_BASELINES: dict[str, tuple[float, float]] = {
    # model_substring: (base_score_0_100, base_power_w)
    "285hx": (125.0, 55.0),
    "275hx": (120.0, 55.0),
    "14900hx": (118.0, 55.0),
    "13980hx": (115.0, 55.0),
    "13950hx": (114.0, 55.0),
    "13900hx": (112.0, 55.0),
    "13900h": (105.0, 45.0),
    "14700hx": (108.0, 55.0),
    "13700hx": (104.0, 55.0),
    "13700h": (95.0, 45.0),
    "12700h": (88.0, 45.0),
    "11800h": (78.0, 45.0),
    "14650hx": (96.0, 55.0),
    "13650hx": (92.0, 55.0),
    "13620h": (86.0, 45.0),
    "13500h": (82.0, 45.0),
    "12500h": (76.0, 45.0),
    "12450h": (70.0, 45.0),
    "13420h": (68.0, 45.0),
    "ultra 9 185h": (98.0, 45.0),
    "ultra 7 155h": (88.0, 28.0),
    "ultra 7 258v": (86.0, 17.0),
    "ultra 7 256v": (84.0, 17.0),
    "ultra 5 125h": (76.0, 28.0),
    "ultra 5 228v": (74.0, 17.0),
    "ultra 5 226v": (72.0, 17.0),
    "1370p": (82.0, 28.0),
    "1360p": (78.0, 28.0),
    "1340p": (72.0, 28.0),
    "1355u": (62.0, 15.0),
    "1255u": (58.0, 15.0),
    "1335u": (56.0, 15.0),
    "1235u": (52.0, 15.0),
    "1215u": (42.0, 15.0),
    "1315u": (44.0, 15.0),
    "1005g1": (28.0, 15.0),
    "7945hx": (122.0, 55.0),
    "8945hs": (102.0, 45.0),
    "8940hx": (118.0, 55.0),
    "7845hx": (108.0, 55.0),
    "7840hs": (94.0, 35.0),
    "7735hs": (82.0, 35.0),
    "7730u": (65.0, 15.0),
    "8845hs": (98.0, 45.0),
    "8745hx": (106.0, 55.0),
    "8645hs": (86.0, 45.0),
    "7640hs": (84.0, 35.0),
    "7535hs": (74.0, 35.0),
    "7530u": (58.0, 15.0),
    "7520u": (45.0, 15.0),
    "7435hs": (70.0, 35.0),
    "7235hs": (60.0, 35.0),
    "5700u": (56.0, 15.0),
    "5500u": (48.0, 15.0),
    "5300u": (38.0, 15.0),
    "3500u": (30.0, 15.0),
}


# -----------------------------------------------------------------------------
# Component Benchmark Resolvers
# -----------------------------------------------------------------------------
def is_integrated_gpu(
    gpu_spec: dict[str, Any] | None,
    gpu_benchmarks: dict[str, Any] | None = None,
) -> bool:
    """Determine whether the GPU is integrated (consumes 0W discrete power)."""
    if not gpu_spec:
        return True

    # 1. Explicit boolean flag in gpu_spec
    if "integrated" in gpu_spec and gpu_spec["integrated"] is not None:
        return bool(gpu_spec["integrated"])

    # 2. Check matched benchmark entry if provided
    raw_model = (gpu_spec.get("model") or "").strip().lower()
    if gpu_benchmarks:
        for key, entry in gpu_benchmarks.items():
            if key.lower() == raw_model or entry.get("model", "").lower() == raw_model:
                if "integrated" in entry and entry["integrated"] is not None:
                    return bool(entry["integrated"])
            patterns = entry.get("match_patterns", [])
            if any(p.lower() == raw_model or p.lower() in raw_model for p in patterns):
                if "integrated" in entry and entry["integrated"] is not None:
                    return bool(entry["integrated"])

    # 3. Common integrated GPU model substrings
    integrated_patterns = [
        "uhd",
        "iris",
        "intel graphics",
        "intel hd",
        "arc 130v",
        "arc 140v",
        "arc 130t",
        "arc 140t",
        "radeon 610m",
        "radeon 660m",
        "radeon 680m",
        "radeon 740m",
        "radeon 760m",
        "radeon 780m",
        "radeon 820m",
        "radeon 880m",
        "radeon 890m",
        "shared",
        "integrated",
    ]
    if any(p in raw_model for p in integrated_patterns):
        return True

    # If discrete keywords exist, definitely discrete
    discrete_patterns = ["rtx", "gtx", "geforce", "radeon rx", "quadro", "arc a", "arc b"]
    if any(p in raw_model for p in discrete_patterns):
        return False

    return False


def resolve_gpu_benchmark(
    gpu_spec: dict[str, Any] | None,
    gpu_benchmarks: dict[str, Any],
) -> tuple[float, float, float]:
    """Resolve GPU base benchmark score, tgp_min, and tgp_max.

    Returns:
        tuple[base_score, tgp_min, tgp_max]
    """
    if not gpu_spec:
        return 1200.0, 15.0, 35.0

    raw_model = (gpu_spec.get("model") or "").strip().lower()

    # 1. Direct key match or alias match in gpu_benchmarks dict
    matched_entry = None
    for key, entry in gpu_benchmarks.items():
        if key.lower() == raw_model or entry.get("model", "").lower() == raw_model:
            matched_entry = entry
            break
        patterns = entry.get("match_patterns", [])
        if any(p.lower() == raw_model or p.lower() in raw_model for p in patterns):
            matched_entry = entry
            break

    if matched_entry:
        is_igpu = is_integrated_gpu(gpu_spec, gpu_benchmarks)
        if is_igpu:
            tgp_min = 0.0
            tgp_max = 0.0
        else:
            tgp_limits = matched_entry.get("tdp_limits") or {}
            tgp_min = float(tgp_limits.get("min_w") or 35.0)
            tgp_max = float(tgp_limits.get("max_w") or 140.0)

        # Prioritize explicit base_score if provided in the JSON entry
        if "base_score" in matched_entry:
            base_score = float(matched_entry["base_score"])
            return base_score, tgp_min, tgp_max

    # 2. Match against curated reference baselines
    for pattern, (b_score, p_min, p_max) in DEFAULT_GPU_BASELINES.items():
        if pattern in raw_model:
            if is_integrated_gpu(gpu_spec, gpu_benchmarks):
                return b_score, 0.0, 0.0
            return b_score, p_min, p_max

    # 3. Fallback based on integrated vs discrete
    if is_integrated_gpu(gpu_spec, gpu_benchmarks):
        return 1200.0, 0.0, 0.0
    return 5000.0, 35.0, 80.0


def resolve_cpu_benchmark(
    cpu_spec: dict[str, Any] | None,
    cpu_benchmarks: dict[str, Any],
) -> tuple[float, float]:
    """Resolve CPU base benchmark score and nominal base_power_w.

    Returns:
        tuple[base_score_0_100, base_power_w]
    """
    if not cpu_spec:
        return 50.0, 28.0

    raw_model = (cpu_spec.get("model") or "").strip().lower()
    spec_base_power = cpu_spec.get("base_power_w")

    # 1. Search in cpu_benchmarks dictionary
    matched_entry = None
    for key, entry in cpu_benchmarks.items():
        if key.lower() == raw_model or entry.get("model", "").lower() == raw_model:
            matched_entry = entry
            break
        aliases = entry.get("aliases", [])
        if any(a.lower() == raw_model or a.lower() in raw_model for a in aliases):
            matched_entry = entry
            break

    if matched_entry:
        entry_base_power = float(matched_entry.get("base_power_w") or spec_base_power or 45.0)
        if "base_score" in matched_entry:
            return float(matched_entry["base_score"]), entry_base_power

    # 2. Match against curated reference baselines
    for pattern, (b_score, b_power) in DEFAULT_CPU_BASELINES.items():
        if pattern in raw_model:
            power = float(spec_base_power or b_power)
            return b_score, power

    # 3. Fallback based on core counts / nominal TDP
    cores = int(cpu_spec.get("cores") or 8)
    base_power = float(spec_base_power or (45.0 if cores >= 8 else 15.0))
    estimated_score = clamp(cores * 6.5, 25.0, 95.0)
    return estimated_score, base_power


# -----------------------------------------------------------------------------
# Metric 1 & 2: Silicon Performance & Electrical Power Sufficiency
# -----------------------------------------------------------------------------
def calculate_silicon_and_power_metrics(
    cpu_spec: dict[str, Any] | None,
    gpu_spec: dict[str, Any] | None,
    power_spec: dict[str, Any] | None,
    cpu_benchmarks: dict[str, Any],
    gpu_benchmarks: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Calculate Metric 1 (Silicon Specs) and Metric 2 (Power Margin)."""
    power_spec = power_spec or {}
    power_adapter_w = power_spec.get("power_adapter_w")
    if power_adapter_w is not None:
        power_adapter_w = float(power_adapter_w)

    base_cpu_score, cpu_base_w = resolve_cpu_benchmark(cpu_spec, cpu_benchmarks)
    base_gpu_raw, tgp_min, tgp_max = resolve_gpu_benchmark(gpu_spec, gpu_benchmarks)

    is_integrated = is_integrated_gpu(gpu_spec, gpu_benchmarks)

    if is_integrated:
        # Integrated GPU consumes 0W discrete power (power envelope shared within CPU package)
        p_actual = 0.0
        tgp_source = "INTEGRATED_GPU"
        scale_factor_gpu = 1.0
    else:
        # Infer P_actual (Configured TGP for discrete GPUs)
        explicit_tgp = (gpu_spec or {}).get("tdp_w")
        if explicit_tgp is not None:
            p_actual = float(explicit_tgp)
            tgp_source = "EXPLICIT_SPEC"
        elif power_adapter_w is not None:
            p_actual = clamp(power_adapter_w - cpu_base_w - 25.0, tgp_min, tgp_max)
            tgp_source = "INFERRED_FROM_CHARGER"
        else:
            p_actual = (tgp_min + tgp_max) / 2.0
            tgp_source = "BENCHMARK_DEFAULT"

        # Effective GPU Score (Guard 1: Normalized by 100)
        if tgp_max > tgp_min:
            scale_factor_gpu = 0.72 + 0.28 * ((p_actual - tgp_min) / (tgp_max - tgp_min))
        else:
            scale_factor_gpu = 1.0

    effective_gpu_score = (base_gpu_raw * scale_factor_gpu) / 100.0

    # Effective CPU Score (Guard 2: power_adapter_w null check)
    if power_adapter_w is None:
        scale_factor_cpu = 1.0
    else:
        p_cpu_avail = power_adapter_w - p_actual - 25.0
        scale_factor_cpu = clamp(p_cpu_avail / cpu_base_w, 0.70, 1.20)

    effective_cpu_score = base_cpu_score * scale_factor_cpu

    # Metric 2: Electrical Power Sufficiency Margin (ΔP)
    if power_adapter_w is None:
        delta_p = 0.0
        electrical_status = "UNKNOWN_CHARGER_NEUTRAL"
    else:
        delta_p = power_adapter_w - (cpu_base_w + p_actual + 25.0)
        electrical_status = "UNCONSTRAINED_HEADROOM" if delta_p >= 0.0 else "DEFICIT_THROTTLED"

    silicon_metrics = {
        "effective_gpu_score": round(effective_gpu_score, 2),
        "effective_cpu_score": round(effective_cpu_score, 2),
        "inferred_tgp_w": round(p_actual, 1),
        "tgp_source": tgp_source,
        "scale_factor_gpu": round(scale_factor_gpu, 3),
        "scale_factor_cpu": round(scale_factor_cpu, 3),
    }

    power_metrics = {
        "delta_p_watts": round(delta_p, 1),
        "electrical_status": electrical_status,
        "power_adapter_w": power_adapter_w,
    }

    return silicon_metrics, power_metrics


# -----------------------------------------------------------------------------
# Metric 3: Display Optics & Quality Index (0 - 100)
# -----------------------------------------------------------------------------
def calculate_display_metrics(display_spec: dict[str, Any] | None) -> dict[str, Any]:
    """Calculate Metric 3 (Display Optics & Quality)."""
    display_spec = display_spec or {}

    w = float(display_spec.get("resolution_width") or 1920)
    h = float(display_spec.get("resolution_height") or 1080)
    size = float(display_spec.get("size_inches") or 15.6)
    ppi = ((w**2 + h**2) ** 0.5) / size if size > 0 else 141.0

    s_ppi = clamp(((ppi - 120.0) / 130.0) * 100.0, 0.0, 100.0)

    hz = float(display_spec.get("refresh_rate_hz") or 60.0)
    s_hz = clamp(((hz - 60.0) / 180.0) * 100.0, 0.0, 100.0)

    # Color Gamut Score
    gamut_str = (display_spec.get("color_gamut") or "").lower()
    if "dci-p3" in gamut_str or "adobe" in gamut_str:
        s_gamut = 100.0
        color_gamut_tier = "PROFESSIONAL_DCI_P3"
    elif "srgb" in gamut_str or "72% ntsc" in gamut_str:
        s_gamut = 80.0
        color_gamut_tier = "STANDARD_SRGB"
    elif "45% ntsc" in gamut_str:
        s_gamut = 35.0
        color_gamut_tier = "BUDGET_WASHED"
    else:
        s_gamut = 50.0
        color_gamut_tier = "UNLISTED_STANDARD"

    # Panel Technology Score
    panel_str = (display_spec.get("panel_type") or "").upper()
    if "OLED" in panel_str or "MINI-LED" in panel_str:
        s_panel = 100.0
        panel_tier = "OLED"
    elif "IPS" in panel_str:
        s_panel = 75.0
        panel_tier = "IPS"
    elif "VA" in panel_str:
        s_panel = 55.0
        panel_tier = "VA"
    elif "TN" in panel_str:
        s_panel = 20.0
        panel_tier = "TN"
    else:
        s_panel = 70.0
        panel_tier = "STANDARD_IPS_LEVEL"

    # Aspect Ratio Score
    aspect = (display_spec.get("aspect_ratio") or "").strip()
    s_aspect = 100.0 if aspect in ("16:10", "3:2") else 60.0

    display_score = (0.30 * s_ppi) + (0.20 * s_hz) + (0.30 * s_gamut) + (0.15 * s_panel) + (0.05 * s_aspect)

    return {
        "display_score": round(display_score, 2),
        "ppi": round(ppi, 1),
        "refresh_rate_hz": hz,
        "panel_technology": panel_tier,
        "color_gamut_tier": color_gamut_tier,
        "aspect_ratio": aspect or "16:9",
    }


# -----------------------------------------------------------------------------
# Metric 4: Endurance & Portability Index (0 - 100)
# -----------------------------------------------------------------------------
def calculate_mobility_metrics(
    power_spec: dict[str, Any] | None,
    physical_spec: dict[str, Any] | None,
    cpu_base_w: float,
) -> dict[str, Any]:
    """Calculate Metric 4 (Endurance & Portability Index)."""
    power_spec = power_spec or {}
    physical_spec = physical_spec or {}

    # Battery runtime (Guard 3: default 50.0 Wh if null)
    battery_wh = power_spec.get("battery_capacity_wh")
    if battery_wh is None:
        battery_wh = 50.0
    else:
        battery_wh = float(battery_wh)

    light_draw_w = 6.0 + (cpu_base_w * 0.20)
    battery_hours_estimate = round(battery_wh / light_draw_w, 2)

    # Portability Index (Guard 3: fallbacks for height_mm and weight_kg)
    weight_kg = physical_spec.get("weight_kg")
    height_mm = physical_spec.get("height_mm")

    if weight_kg is None:
        portability_score = 50.0
        portability_tier = "BALANCED"
    elif height_mm is not None:
        weight_kg = float(weight_kg)
        height_mm = float(height_mm)
        raw_score = 100.0 - (50.0 * ((weight_kg - 1.0) / 2.5) + 50.0 * ((height_mm - 12.0) / 18.0))
        portability_score = clamp(raw_score, 0.0, 100.0)
    else:
        # Fallback when height_mm is null: 100% weight on weight_kg
        weight_kg = float(weight_kg)
        raw_score = 100.0 - (100.0 * ((weight_kg - 1.0) / 2.5))
        portability_score = clamp(raw_score, 0.0, 100.0)

    if portability_score >= 80.0:
        portability_tier = "ULTRAPORTABLE"
    elif portability_score >= 50.0:
        portability_tier = "BALANCED"
    else:
        portability_tier = "DESK_BOUND"

    return {
        "portability_score": round(portability_score, 2),
        "portability_tier": portability_tier,
        "battery_hours_estimate": battery_hours_estimate,
        "battery_capacity_wh": battery_wh,
        "weight_kg": weight_kg,
    }


# -----------------------------------------------------------------------------
# Metric 5: Upgradeability & Hardware Longevity (0 - 100)
# -----------------------------------------------------------------------------
def calculate_longevity_metrics(
    memory_spec: dict[str, Any] | None,
    storage_spec: dict[str, Any] | None,
    connectivity_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    """Calculate Metric 5 (Upgradeability & Longevity Rating)."""
    memory_spec = memory_spec or {}
    storage_spec = storage_spec or {}
    connectivity_spec = connectivity_spec or {}

    # RAM Expansion (Max 45 pts)
    is_soldered = bool(memory_spec.get("is_soldered", False))
    slot_count = int(memory_spec.get("slot_count") or 1)
    ram_gb = int(memory_spec.get("capacity_gb") or 16)

    if not is_soldered and slot_count >= 2:
        s_ram = 45.0
        ram_upgradeable = True
    elif not is_soldered and slot_count == 1:
        s_ram = 25.0
        ram_upgradeable = True
    elif is_soldered and ram_gb >= 32:
        s_ram = 15.0
        ram_upgradeable = False
    elif is_soldered and ram_gb >= 16:
        s_ram = 8.0
        ram_upgradeable = False
    else:
        s_ram = 0.0
        ram_upgradeable = False

    # Storage Expansion (Max 35 pts)
    m2_slots = int(storage_spec.get("slot_count") or 1)
    if m2_slots >= 2:
        s_storage = 35.0
        dual_m2 = True
    elif m2_slots == 1:
        s_storage = 20.0
        dual_m2 = False
    else:
        s_storage = 10.0
        dual_m2 = False

    # High-Speed External Bus (Max 20 pts)
    tb_version = connectivity_spec.get("thunderbolt_version")
    ports_raw = str(connectivity_spec.get("ports") or "").lower()

    has_tb = bool(tb_version) or "thunderbolt" in ports_raw or "usb4" in ports_raw
    has_usbc_dp = "displayport" in ports_raw or "power delivery" in ports_raw or "type-c" in ports_raw

    if has_tb:
        s_bus = 20.0
        has_high_speed_bus = True
    elif has_usbc_dp:
        s_bus = 10.0
        has_high_speed_bus = True
    else:
        s_bus = 0.0
        has_high_speed_bus = False

    upgradeability_score = s_ram + s_storage + s_bus

    if upgradeability_score >= 80.0:
        upgradeability_tier = "MAXIMUM_UPGRADEABLE"
    elif upgradeability_score >= 40.0:
        upgradeability_tier = "MODERATE_EXPANSION"
    else:
        upgradeability_tier = "LOCKED_APPLIANCE"

    return {
        "upgradeability_score": round(upgradeability_score, 2),
        "upgradeability_tier": upgradeability_tier,
        "ram_upgradeable": ram_upgradeable,
        "dual_m2_storage": dual_m2,
        "has_high_speed_bus": has_high_speed_bus,
    }


# -----------------------------------------------------------------------------
# Metric 6: Market Pricing & Retailer Economics
# -----------------------------------------------------------------------------
def calculate_economics_metrics(
    offers: list[dict[str, Any]] | None,
    effective_gpu_score: float,
    effective_cpu_score: float,
    ram_gb: int,
) -> dict[str, Any]:
    """Calculate Metric 6 (Retailer Economics & Value Ratio)."""
    offers = offers or []
    valid_offers = [
        o
        for o in offers
        if o.get("price_egp") and float(o["price_egp"]) > 0 and o.get("in_stock", o.get("is_available", True))
    ]

    if not valid_offers:
        # Fallback to any offer with price if none explicitly marked in stock
        valid_offers = [o for o in offers if o.get("price_egp") and float(o["price_egp"]) > 0]

    if valid_offers:
        prices = [float(o["price_egp"]) for o in valid_offers]
        min_price = min(prices)
        max_price = max(prices)
        price_spread = max_price - min_price
        cheapest_offer = next(o for o in valid_offers if float(o["price_egp"]) == min_price)
        cheapest_store = (
            cheapest_offer.get("store_name") or cheapest_offer.get("store") or cheapest_offer.get("store_key")
        )

        hardware_composite = effective_gpu_score + effective_cpu_score + (ram_gb * 1.5)
        value_ratio = round((hardware_composite / min_price) * 100_000.0, 2)
    else:
        min_price = None
        max_price = None
        price_spread = 0.0
        cheapest_store = None
        value_ratio = None

    return {
        "min_price_egp": min_price,
        "cheapest_store": cheapest_store,
        "max_price_egp": max_price,
        "price_spread_egp": round(price_spread, 2),
        "active_offers_count": len(valid_offers),
        "value_ratio": value_ratio,
    }


# -----------------------------------------------------------------------------
# Main Composite Evaluator
# -----------------------------------------------------------------------------
VERIFIED_METRICS_STATUSES = {
    "VERIFIED_ICECAT",
    "VERIFIED_ICECAT_VARIANT",
    "LLM_EXTRACTED",
}


def is_laptop_verified_for_metrics(laptop: dict[str, Any]) -> bool:
    """Return True if the laptop is verified to enter the hardware metrics phase.

    If `verification_status` is explicitly present, requires it to be one of
    `VERIFIED_ICECAT`, `VERIFIED_ICECAT_VARIANT`, or `LLM_EXTRACTED`.
    Laptops marked `NOT_FOUND` are held back until verified.
    """
    status = laptop.get("verification_status")
    if status is None:
        return True
    return str(status).upper() in VERIFIED_METRICS_STATUSES


def calculate_all_hardware_metrics(
    laptop: dict[str, Any],
    cpu_benchmarks: dict[str, Any],
    gpu_benchmarks: dict[str, Any],
) -> dict[str, Any]:
    """Compute the 6 objective hardware metrics for a single canonical laptop."""
    specs = laptop.get("specs", {}) or {}
    cpu_spec = specs.get("cpu")
    gpu_spec = specs.get("gpu")
    power_spec = specs.get("power_battery")
    display_spec = specs.get("display")
    physical_spec = specs.get("physical")
    memory_spec = specs.get("memory")
    storage_spec = specs.get("storage")
    connectivity_spec = specs.get("connectivity")
    offers = laptop.get("offers", []) or []

    # 1 & 2. Silicon and Power
    silicon_metrics, power_metrics = calculate_silicon_and_power_metrics(
        cpu_spec=cpu_spec,
        gpu_spec=gpu_spec,
        power_spec=power_spec,
        cpu_benchmarks=cpu_benchmarks,
        gpu_benchmarks=gpu_benchmarks,
    )

    # 3. Display
    display_metrics = calculate_display_metrics(display_spec)

    # 4. Mobility
    _, cpu_base_w = resolve_cpu_benchmark(cpu_spec, cpu_benchmarks)
    mobility_metrics = calculate_mobility_metrics(
        power_spec=power_spec,
        physical_spec=physical_spec,
        cpu_base_w=cpu_base_w,
    )

    # 5. Longevity
    longevity_metrics = calculate_longevity_metrics(
        memory_spec=memory_spec,
        storage_spec=storage_spec,
        connectivity_spec=connectivity_spec,
    )

    # 6. Economics
    ram_gb = int((memory_spec or {}).get("capacity_gb") or 16)
    economics_metrics = calculate_economics_metrics(
        offers=offers,
        effective_gpu_score=silicon_metrics["effective_gpu_score"],
        effective_cpu_score=silicon_metrics["effective_cpu_score"],
        ram_gb=ram_gb,
    )

    return {
        "silicon": silicon_metrics,
        "power": power_metrics,
        "display": display_metrics,
        "mobility": mobility_metrics,
        "longevity": longevity_metrics,
        "economics": economics_metrics,
    }
