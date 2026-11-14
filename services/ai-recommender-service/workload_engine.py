#!/usr/bin/env python3
"""
Deterministic Workload & Career Track Evaluation Engine (workload_engine.py)
----------------------------------------------------------------------------
Maps structured hardware and `derived_metrics` into realistic 1080p gaming FPS
estimates, creative/engineering software readiness, and career track suitability.
"""
from typing import Dict, Any, List


def _classify_fps_tier(fps: int) -> str:
    if fps >= 120:
        return "Ultra/Competitive 120+ FPS"
    if fps >= 80:
        return "High 80-119 FPS"
    if fps >= 50:
        return "Medium-High 50-79 FPS"
    return "Entry/Low <50 FPS"


def _classify_software_tier(score: float) -> str:
    if score >= 82.0:
        return "Pro / Heavy Projects"
    if score >= 62.0:
        return "Smooth / Intermediate"
    if score >= 42.0:
        return "Light / Learning"
    return "Not Recommended"


def _build_game_entry(
    name: str,
    estimated_fps: int,
    refresh_rate_hz: int,
    settings_label: str,
    modes: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    bottleneck = estimated_fps > refresh_rate_hz
    entry: Dict[str, Any] = {
        "name": name,
        "resolution": "1080p",
        "settings": settings_label,
        "estimated_fps": estimated_fps,
        "tier": _classify_fps_tier(estimated_fps),
        "screen_bottleneck": bottleneck,
    }
    if modes:
        entry["modes"] = modes
    if bottleneck:
        entry["screen_bottleneck_note"] = (
            f"GPU renders ~{estimated_fps} FPS, but the {refresh_rate_hz}Hz panel caps visible output at {refresh_rate_hz} FPS."
        )
        entry["screen_bottleneck_note_ar"] = (
            f"الكارت يولد حوالي {estimated_fps} فريم، لكن الشاشة بتردد {refresh_rate_hz}Hz تحد العرض المرئي عند {refresh_rate_hz} فريم."
        )
    else:
        entry["screen_bottleneck_note"] = None
        entry["screen_bottleneck_note_ar"] = None
    return entry


def evaluate_workloads(laptop: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates a laptop across 6 role-model games (1080p), 6 role-model software
    suites, and 5 career tracks deterministically from `specs` & `derived_metrics`.
    """
    dm = laptop.get("derived_metrics", {})
    ti = dm.get("topsis_inputs", {})
    silicon = dm.get("silicon", {})
    disp = dm.get("display", {})
    long_m = dm.get("longevity", {})
    conn = dm.get("connectivity_index", {})
    specs = laptop.get("specs", {})

    cpu_score = float(ti.get("cpu_score") or silicon.get("effective_cpu_score") or 40.0)
    gpu_score = float(ti.get("gpu_score") or silicon.get("effective_gpu_score") or 10.0)
    inferred_tgp_w = float(silicon.get("inferred_tgp_w") or specs.get("gpu", {}).get("tdp_w") or 15.0)
    is_igpu = bool(specs.get("gpu", {}).get("integrated", True))
    vram_gb = float(specs.get("gpu", {}).get("vram_gb") or (0.0 if is_igpu else 4.0))

    gpu_mfg = str(specs.get("gpu", {}).get("manufacturer") or "").upper()
    gpu_model = str(specs.get("gpu", {}).get("model") or "")
    has_cuda = ("NVIDIA" in gpu_mfg or "RTX" in gpu_model.upper() or "GTX" in gpu_model.upper()) and not is_igpu

    ram_gb = int(specs.get("memory", {}).get("capacity_gb") or 8)
    ram_upgradeable = bool(long_m.get("ram_upgradeable", False))
    max_ram_gb = int(long_m.get("max_ram_gb") or ram_gb)

    refresh_rate_hz = int(disp.get("refresh_rate_hz") or specs.get("display", {}).get("refresh_rate_hz") or 60)
    color_gamut_tier = str(disp.get("color_gamut_tier") or specs.get("display", {}).get("color_gamut") or "45% NTSC (Basic)")
    is_low_gamut = "45% ntsc" in color_gamut_tier.lower()
    has_ethernet = bool(conn.get("has_ethernet", specs.get("connectivity", {}).get("ethernet", False)))

    cpu_info = specs.get("cpu", {})
    cpu_arch_str = f"{cpu_info.get('manufacturer', '')} {cpu_info.get('line', '')} {cpu_info.get('microarchitecture', '')}".lower()
    is_arm = any(tok in cpu_arch_str for tok in ["qualcomm", "snapdragon", "oryon", "arm", "apple"])
    cpu_architecture = "ARM64" if is_arm else "x86_64"

    # Multipliers for GPU wattage headroom and VRAM capacity
    tgp_factor = min(1.18, max(0.72, 0.72 + (inferred_tgp_w / 140.0) * 0.42))
    vram_factor = 1.08 if vram_gb >= 8 else (0.95 if vram_gb >= 6 else (0.78 if vram_gb >= 4 else 0.50))

    # -------------------------------------------------------------------------
    # 1. 6 Role-Model Games (1080p)
    # -------------------------------------------------------------------------
    valorant_fps = int(round(max(45.0, min(420.0, 35.0 + (cpu_score * 1.65) + (gpu_score * 1.95)))))

    fortnite_comp_fps = int(round(max(38.0, min(320.0, 25.0 + (cpu_score * 0.95) + (gpu_score * 1.95) * (0.90 + 0.10 * tgp_factor)))))
    fortnite_dx12_fps = int(round(max(18.0, min(180.0, (gpu_score * 1.28 * tgp_factor) + (cpu_score * 0.18) - (12.0 if is_igpu else 0.0)))))

    gtav_fps = int(round(max(22.0, min(210.0, 14.0 + (gpu_score * 1.55 * tgp_factor) + (cpu_score * 0.25)))))

    mc_vanilla_fps = int(round(max(55.0, min(450.0, 45.0 + (cpu_score * 1.85) + (gpu_score * 1.75)))))
    mc_shaders_fps = int(round(max(12.0, min(145.0, (gpu_score * 1.05 * tgp_factor * vram_factor) - (10.0 if is_igpu else 0.0)))))

    rdr2_fps = int(round(max(15.0, min(145.0, (gpu_score * 1.08 * tgp_factor) + (cpu_score * 0.14) - (8.0 if vram_gb < 4 else 0.0)))))

    cp2077_fps = int(round(max(12.0, min(135.0, (gpu_score * 0.98 * tgp_factor * vram_factor) + (cpu_score * 0.12)))))

    if is_arm:
        # Windows on ARM emulation penalty / compatibility caveat for heavy DX12 games
        valorant_fps = int(round(valorant_fps * 0.65))
        fortnite_comp_fps = int(round(fortnite_comp_fps * 0.65))
        fortnite_dx12_fps = int(round(fortnite_dx12_fps * 0.60))
        gtav_fps = int(round(gtav_fps * 0.70))
        rdr2_fps = int(round(rdr2_fps * 0.55))
        cp2077_fps = int(round(cp2077_fps * 0.50))

    games_1080p: List[Dict[str, Any]] = [
        _build_game_entry("Valorant", valorant_fps, refresh_rate_hz, "Competitive Low/High"),
        _build_game_entry(
            "Fortnite",
            fortnite_comp_fps,
            refresh_rate_hz,
            "Competitive Performance Mode",
            modes={
                "competitive": {"fps": fortnite_comp_fps, "tier": _classify_fps_tier(fortnite_comp_fps)},
                "high_dx12": {"fps": fortnite_dx12_fps, "tier": _classify_fps_tier(fortnite_dx12_fps)},
            },
        ),
        _build_game_entry("GTA V", gtav_fps, refresh_rate_hz, "Very High"),
        _build_game_entry(
            "Minecraft",
            mc_vanilla_fps,
            refresh_rate_hz,
            "Vanilla Fancy",
            modes={
                "vanilla": {"fps": mc_vanilla_fps, "tier": _classify_fps_tier(mc_vanilla_fps)},
                "shaders_rtx": {"fps": mc_shaders_fps, "tier": _classify_fps_tier(mc_shaders_fps)},
            },
        ),
        _build_game_entry("Red Dead Redemption 2", rdr2_fps, refresh_rate_hz, "Medium-High / Balanced"),
        _build_game_entry("Cyberpunk 2077", cp2077_fps, refresh_rate_hz, "High (FSR/DLSS Balanced)"),
    ]

    # -------------------------------------------------------------------------
    # 2. 6 Role-Model Software
    # -------------------------------------------------------------------------
    ram_bonus = 10.0 if ram_gb >= 32 else (4.0 if ram_gb >= 16 else -12.0)

    premiere_score = round(min(100.0, max(15.0, cpu_score * 0.52 + gpu_score * 0.35 + (vram_gb * 1.5) + ram_bonus)), 1)
    davinci_score = round(min(100.0, max(12.0, gpu_score * 0.58 + cpu_score * 0.25 + (vram_gb * 2.2) + ram_bonus)), 1)
    ae_ps_score = round(min(100.0, max(18.0, cpu_score * 0.62 + gpu_score * 0.22 + ram_bonus * 1.2)), 1)
    autocad_score = round(min(100.0, max(20.0, cpu_score * 0.65 + gpu_score * 0.25 + (4.0 if ram_gb >= 16 else -6.0))), 1)
    solidworks_score = round(min(100.0, max(15.0, cpu_score * 0.45 + gpu_score * 0.42 + (vram_gb * 1.8) + (4.0 if not is_igpu else -12.0))), 1)
    blender_score = round(min(100.0, max(10.0, gpu_score * 0.62 + cpu_score * 0.22 + (vram_gb * 2.0) + (8.0 if has_cuda else -8.0))), 1)

    if is_arm:
        autocad_score = round(autocad_score * 0.72, 1)
        solidworks_score = round(solidworks_score * 0.60, 1)
        blender_score = round(blender_score * 0.65, 1)

    software_benchmarks: List[Dict[str, Any]] = [
        {
            "name": "Adobe Premiere Pro",
            "readiness_score": premiere_score,
            "tier": _classify_software_tier(premiere_score),
            "notes": "4K timeline playback & hardware encode" if premiere_score >= 78 else "Smooth 1080p editing; heavy 4K requires proxy workflow",
        },
        {
            "name": "DaVinci Resolve",
            "readiness_score": davinci_score,
            "tier": _classify_software_tier(davinci_score),
            "display_color_warning": is_low_gamut,
            "color_warning_note": (
                f"Screen is rated {color_gamut_tier}; accurate color grading requires 100% sRGB/DCI-P3 or an external monitor."
                if is_low_gamut else None
            ),
            "color_warning_note_ar": (
                f"الشاشة بتغطية {color_gamut_tier} فقط؛ تصحيح الألوان الدقيق يحتاج شاشة 100% sRGB أو شاشة خارجية."
                if is_low_gamut else None
            ),
            "notes": "Fusion/Color grading benefits from >=6GB VRAM" if vram_gb < 6 else "Ready for GPU-accelerated Fusion & Color grading",
        },
        {
            "name": "Adobe After Effects / Photoshop",
            "readiness_score": ae_ps_score,
            "tier": _classify_software_tier(ae_ps_score),
            "notes": "Heavy RAM & single-core sensitive" if ram_gb < 16 else "Well-suited for layered compositing and motion graphics",
        },
        {
            "name": "AutoCAD",
            "readiness_score": autocad_score,
            "tier": _classify_software_tier(autocad_score),
            "notes": "Requires x86_64 Windows compatibility for full plugin support" if is_arm else "Smooth 2D drafting and moderate 3D CAD",
        },
        {
            "name": "SolidWorks / Revit",
            "readiness_score": solidworks_score,
            "tier": _classify_software_tier(solidworks_score),
            "notes": (
                "ARM64 lacks native SolidWorks support" if is_arm
                else ("Dedicated GPU recommended for large assemblies" if is_igpu else "Capable of multi-part 3D assemblies & BIM models")
            ),
        },
        {
            "name": "Blender (3D Render)",
            "readiness_score": blender_score,
            "tier": _classify_software_tier(blender_score),
            "notes": "Cycles OptiX CUDA acceleration supported" if has_cuda else "No NVIDIA CUDA/OptiX; rendering relies on CPU/iGPU",
        },
    ]

    # -------------------------------------------------------------------------
    # 3. 5 Career Tracks
    # -------------------------------------------------------------------------
    # Track 1: Full-Stack & Mobile Dev
    if is_arm:
        fs_suitability = "Conditional (Web/JS/Python OK; Unsuitable for heavy x86 DevOps/Docker)"
        fs_score = round(min(74.0, cpu_score * 0.55 + (15.0 if ram_gb >= 16 else 5.0)), 1)
        fs_notes = (
            "ARM / Snapdragon delivers great battery life and native web dev/VS Code speed, "
            "but is unsuitable for heavy x86 DevOps, Docker x86 containers, or local x86 VMs."
        )
        fs_notes_ar = (
            "معالج ARM / Snapdragon ممتاز للبطارية وتطوير الويب الخفيف، لكنه غير مناسب لأحمال DevOps الثقيلة أو حاويات Docker x86 والأنظمة الوهمية."
        )
    else:
        fs_score = round(min(100.0, cpu_score * 0.65 + (18.0 if ram_gb >= 16 else 8.0) + (12.0 if ram_upgradeable else 4.0)), 1)
        fs_suitability = "Recommended" if fs_score >= 70.0 else "Entry / Moderate"
        fs_notes = "Full x86_64 support for Docker, Android Studio emulators, and local databases."
        fs_notes_ar = "معمارية x86_64 متوافقة بالكامل مع Docker ومحاكيات الأندرويد وقواعد البيانات."

    # Track 2: AI / ML & Data Science
    local_training_ready = (vram_gb >= 6) and has_cuda
    if local_training_ready:
        ai_score = round(min(100.0, gpu_score * 0.50 + cpu_score * 0.30 + (vram_gb * 2.2) + (6.0 if ram_gb >= 16 else 0.0)), 1)
        ai_suitability = "Recommended (Local CUDA Training Ready)"
        ai_notes = f"NVIDIA CUDA GPU with {int(vram_gb)}GB VRAM supports PyTorch/TensorFlow local training & fine-tuning."
        ai_notes_ar = f"كارت NVIDIA بذاكرة {int(vram_gb)} جيجا VRAM يدعم التدريب المحلي لموديلات PyTorch وTensorFlow."
    else:
        ai_score = round(min(48.0, cpu_score * 0.35 + gpu_score * 0.15), 1)
        ai_suitability = "Cloud-Only (Unsuitable for Local Training)"
        if not has_cuda:
            ai_notes = "Lacks an NVIDIA CUDA GPU (>=6GB VRAM required for local training); use cloud GPUs (Colab/Kaggle)."
            ai_notes_ar = "يفتقر إلى كارت NVIDIA CUDA (مطلوب 6 جيجا VRAM على الأقل للتدريب المحلي)؛ يصلح فقط للشغل السحابي."
        else:
            ai_notes = f"Only {int(vram_gb)}GB VRAM (<6GB minimum); insufficient for local deep learning training."
            ai_notes_ar = f"ذاكرة الكارت {int(vram_gb)} جيجا فقط (الحد الأدنى 6 جيجا VRAM)؛ غير كافية لتدريب نماذج الذكاء الاصطناعي محلياً."

    # Track 3: Cybersecurity & Pentesting
    cyber_ram_ok = (ram_gb >= 16) or (ram_upgradeable and max_ram_gb >= 16)
    cyber_arch_ok = cpu_architecture == "x86_64"
    if is_arm:
        cyber_score = 30.0
        cyber_suitability = "Unsuitable (ARM64 Limitation)"
        cyber_notes = "ARM / Snapdragon is unsuitable for x86 Kali/Parrot VMs, nested virtualization, and many pentesting tools."
        cyber_notes_ar = "معالج ARM / Snapdragon غير مناسب لتشغيل أنظمة Kali الوهمية وأدوات اختبار الاختراق المبنية على x86."
    else:
        cyber_score = round(
            min(
                100.0,
                cpu_score * 0.50
                + (22.0 if ram_gb >= 16 else (14.0 if cyber_ram_ok else 4.0))
                + (15.0 if has_ethernet else 0.0)
                + 10.0,
            ),
            1,
        )
        if cyber_ram_ok and has_ethernet and cyber_arch_ok:
            cyber_suitability = "Recommended"
        elif cyber_ram_ok and cyber_arch_ok:
            cyber_suitability = "Good (USB-Ethernet Adapter Needed)"
        else:
            cyber_suitability = "Limited (Insufficient RAM/Upgradeability)"
        cyber_notes = (
            f"x86_64 CPU, {'RJ-45 Ethernet present' if has_ethernet else 'no built-in RJ-45 port'}, "
            f"{'16GB+ RAM or upgradeable' if cyber_ram_ok else 'RAM capped below 16GB'}."
        )
        cyber_notes_ar = (
            f"معمارية x86_64، {'منفذ شبكة RJ-45 مدمج' if has_ethernet else 'بدون منفذ RJ-45 مدمج'}، "
            f"{'رام 16 جيجا أو قابلة للترقية' if cyber_ram_ok else 'الرام محدودة أقل من 16 جيجا'}."
        )

    # Track 4: Pro Video & Motion Design
    pv_score = round((premiere_score + davinci_score + ae_ps_score) / 3.0, 1)
    if is_low_gamut:
        pv_suitability = "Hardware Only (Screen Color Warning: 45% NTSC)"
    elif pv_score >= 75.0:
        pv_suitability = "Recommended"
    else:
        pv_suitability = "Entry / 1080p Editing"

    # Track 5: Data Analysis & Business
    dab_score = round(min(100.0, cpu_score * 0.55 + float(ti.get("mobility_score") or 50.0) * 0.25 + (15.0 if ram_gb >= 16 else 8.0)), 1)
    dab_suitability = "Recommended" if dab_score >= 65.0 else "Adequate"

    career_tracks: List[Dict[str, Any]] = [
        {
            "track": "Full-Stack & Mobile Dev",
            "suitability": fs_suitability,
            "score": fs_score,
            "arm_flag": is_arm,
            "notes": fs_notes,
            "notes_ar": fs_notes_ar,
        },
        {
            "track": "AI / ML & Data Science",
            "suitability": ai_suitability,
            "score": ai_score,
            "local_training_ready": local_training_ready,
            "vram_gb": int(vram_gb),
            "has_cuda": has_cuda,
            "notes": ai_notes,
            "notes_ar": ai_notes_ar,
        },
        {
            "track": "Cybersecurity & Pentesting",
            "suitability": cyber_suitability,
            "score": cyber_score,
            "x86_64": cyber_arch_ok,
            "has_ethernet": has_ethernet,
            "ram_16gb_or_upgradeable": cyber_ram_ok,
            "notes": cyber_notes,
            "notes_ar": cyber_notes_ar,
        },
        {
            "track": "Pro Video & Motion Design",
            "suitability": pv_suitability,
            "score": pv_score,
            "display_color_warning": is_low_gamut,
            "color_gamut_tier": color_gamut_tier,
            "notes": "100% sRGB/DCI-P3 panel suitable for color work" if not is_low_gamut else f"Low color gamut ({color_gamut_tier}); external monitor advised for grading.",
            "notes_ar": "ألوان الشاشة دقيقة ومناسبة للمونتاج والتصميم" if not is_low_gamut else f"دقة ألوان الشاشة محدودة ({color_gamut_tier})؛ يُنصح بشاشة خارجية للألوان.",
        },
        {
            "track": "Data Analysis & Business",
            "suitability": dab_suitability,
            "score": dab_score,
            "notes": "Handles Power BI, large Excel sheets, SQL, and dashboards smoothly.",
            "notes_ar": "مناسب لبرامج Power BI وملفات Excel الكبيرة وقواعد البيانات ولوحات التحكم.",
        },
    ]

    return {
        "hardware_context": {
            "cpu_architecture": cpu_architecture,
            "is_arm": is_arm,
            "ram_gb": ram_gb,
            "ram_upgradeable": ram_upgradeable,
            "vram_gb": int(vram_gb),
            "has_cuda": has_cuda,
            "inferred_tgp_w": int(round(inferred_tgp_w)),
            "refresh_rate_hz": refresh_rate_hz,
            "color_gamut_tier": color_gamut_tier,
            "has_ethernet": has_ethernet,
        },
        "games_1080p": games_1080p,
        "software_benchmarks": software_benchmarks,
        "career_tracks": career_tracks,
    }
