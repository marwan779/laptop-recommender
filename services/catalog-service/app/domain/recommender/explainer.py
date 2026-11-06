"""Explainable recommendation badge and reason generator.

Builds localized (Arabic and English) explanation points explaining why a laptop
was recommended, highlighting key hardware strengths, display quality, battery,
upgradeability, and cross-store savings.
"""

from typing import Any


def build_why_recommended(laptop: dict[str, Any], persona: str) -> dict[str, list[str]]:
    """Build localized bullet points explaining why this laptop was chosen."""
    s = laptop.get("specs") or {}
    dm = laptop.get("derived_metrics") or {}
    reasons_ar: list[str] = []
    reasons_en: list[str] = []

    cpu = s.get("cpu") or {}
    gpu = s.get("gpu") or {}
    memory = s.get("memory") or {}
    storage = s.get("storage") or {}
    display = s.get("display") or {}

    silicon_dm = dm.get("silicon") or {}
    display_dm = dm.get("display") or {}
    mobility_dm = dm.get("mobility") or {}
    longevity_dm = dm.get("longevity") or {}
    topsis_inputs = dm.get("topsis_inputs") or {}

    # CPU & GPU Highlight
    cpu_name = cpu.get("full_name") or cpu.get("model") or "High-Performance CPU"
    cores = cpu.get("cores")
    boost = cpu.get("clock_boost_ghz")
    gpu_model = gpu.get("model")
    is_igpu = gpu.get("integrated", True)
    tgp = silicon_dm.get("inferred_tgp_w")
    vram = gpu.get("vram_gb")
    ram_gb = memory.get("capacity_gb")
    mem_type = memory.get("memory_type", "RAM")
    ssd_gb = storage.get("capacity_gb")
    ssd_str = f"{ssd_gb // 1024}TB" if (ssd_gb and ssd_gb >= 1024) else f"{ssd_gb}GB"

    if not is_igpu and gpu_model:
        tgp_str = f"{int(tgp)}W" if tgp else ""
        reasons_ar.append(f"كارت شاشة {gpu_model} ({vram}GB) بقدرة {tgp_str} ومعالج {cpu_name}")
        reasons_en.append(f"{gpu_model} ({vram}GB, {tgp_str} TGP) paired with {cpu_name}")
    else:
        reasons_ar.append(f"معالج {cpu_name} ({cores} أنوية حتى {boost}GHz) مع رام {ram_gb}GB {mem_type}")
        reasons_en.append(f"{cpu_name} ({cores}C, up to {boost}GHz) with {ram_gb}GB {mem_type} RAM")

    # Display highlight
    disp_size = display.get("size_inches")
    panel = display_dm.get("panel_technology") or display.get("panel_type") or "IPS"
    hz = display_dm.get("refresh_rate_hz") or display.get("refresh_rate_hz") or 60
    gamut = str(display_dm.get("color_gamut_tier", "")).split(" (")[0] or "Standard"
    reasons_ar.append(f"شاشة {disp_size} بوصة {panel} بتردد {hz}Hz وتغطية ألوان {gamut}")
    reasons_en.append(f"{disp_size}-inch {panel} {hz}Hz display ({gamut})")

    # Persona-specific 3rd highlight
    if persona in ["student_and_office", "business_and_mobility"]:
        w_kg = mobility_dm.get("weight_kg")
        b_hrs = mobility_dm.get("battery_hours_estimate")
        reasons_ar.append(f"وزن خفيف {w_kg} كجم وبطارية تدوم حوالي {b_hrs} ساعات مع تخزين {ssd_str} SSD")
        reasons_en.append(f"Lightweight {w_kg} kg chassis with ~{b_hrs}h battery life & {ssd_str} SSD")
    else:
        m2_slots = longevity_dm.get("total_m2_slots") or 1
        max_r = longevity_dm.get("max_ram_gb") or ram_gb
        reasons_ar.append(f"رام {ram_gb}GB {mem_type} (تقبل حتى {max_r}GB) وتخزين {ssd_str} ({m2_slots} فتحات M.2)")
        reasons_en.append(f"{ram_gb}GB {mem_type} RAM (up to {max_r}GB) & {ssd_str} SSD ({m2_slots}x M.2 slots)")

    # Store & Price spread highlight
    price = topsis_inputs.get("effective_price_egp") or laptop.get("min_price_egp")
    store = laptop.get("cheapest_store", "unknown")
    spread = laptop.get("price_spread_egp") or 0
    if spread >= 1000 and price:
        reasons_ar.append(f"أفضل سعر متاح لدى {store} ({price:,.0f} ج.م) بتوفير {spread:,.0f} ج.م عن أعلى متجر")
        reasons_en.append(f"Best price at {store} ({price:,.0f} EGP), saving {spread:,.0f} EGP across stores")
    elif price:
        reasons_ar.append(f"متاح بسعر {price:,.0f} ج.م لدى {store}")
        reasons_en.append(f"Available at {price:,.0f} EGP via {store}")

    return {"ar": reasons_ar, "en": reasons_en}
