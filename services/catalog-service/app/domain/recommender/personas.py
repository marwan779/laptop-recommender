"""Persona definitions, criteria configuration, and bilingual prompt parsing.

Defines the 16 specialized user personas (plus 5 legacy aliases), the 14-column
TOPSIS criteria configuration, implicit hardware gates, and the bilingual
(Arabic/English) text prompt parser.
"""

import copy
from enum import StrEnum
import re
from typing import Any

# =============================================================================
# 1. TOPSIS CRITERIA & BENEFIT/COST KEYS (14-Column Matrix)
# =============================================================================
TOPSIS_CRITERIA_KEYS: list[str] = [
    "cpu_score",
    "gpu_compute_score",
    "vram_score",
    "power_therm_score",
    "display_gaming_score",
    "display_creator_score",
    "battery_score",
    "portability_score",
    "upgradeability_score",
    "build_quality_score",
    "ergonomics_score",
    "connectivity_score",
    "community_nlp_score",
    "effective_price_egp",
]

# True = Benefit (higher is better), False = Cost (lower is better)
IS_BENEFIT_CRITERION: list[bool] = [True] * 13 + [False]


class PersonaType(StrEnum):
    """The 16 official personas supported by the recommender engine (plus 5 legacy aliases)."""

    GAMING = "gaming"
    GAMING_ESPORTS = "gaming_esports"
    GAMING_AAA = "gaming_aaa"
    GAMING_BUDGET = "gaming_budget"
    CREATIVE = "creative"
    CREATIVE_VIDEO = "creative_video"
    CREATIVE_2D_PHOTO = "creative_2d_photo"
    CREATIVE_3D_CAD_GAMEDEV = "creative_3d_cad_gamedev"
    TECH = "tech"
    TECH_AI_ML = "tech_ai_ml"
    TECH_WEB_MOBILE = "tech_web_mobile"
    TECH_CYBER_VMS = "tech_cyber_vms"
    BALANCED = "balanced"
    DAILY_STUDENT = "daily_student"
    DAILY_BUSINESS = "daily_business"
    DAILY_OFFICE = "daily_office"

    # Legacy aliases kept for backwards-compatible request validation
    AI_AND_GAME_DEV = "ai_and_game_dev"
    PROGRAMMING = "programming"
    CONTENT_CREATION = "content_creation"
    STUDENT_AND_OFFICE = "student_and_office"
    BUSINESS_AND_MOBILITY = "business_and_mobility"


LEGACY_PERSONA_ALIASES: dict[str, str] = {
    "ai_and_game_dev": "tech_ai_ml",
    "programming": "tech_web_mobile",
    "content_creation": "creative",
    "student_and_office": "daily_student",
    "business_and_mobility": "daily_business",
}

PERSONA_CONFIGS: dict[str, dict[str, Any]] = {
    "gaming": {
        "label_ar": "الألعاب (عام)",
        "label_en": "Gaming (Main)",
        "weights": {
            "cpu_score": 0.15,
            "gpu_compute_score": 0.27,
            "vram_score": 0.10,
            "power_therm_score": 0.12,
            "display_gaming_score": 0.12,
            "display_creator_score": 0.03,
            "battery_score": 0.01,
            "portability_score": 0.01,
            "upgradeability_score": 0.04,
            "build_quality_score": 0.03,
            "ergonomics_score": 0.01,
            "connectivity_score": 0.01,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "min_refresh_hz": 120,
            "min_ram_gb": 8,
        },
    },
    "gaming_esports": {
        "label_ar": "ألعاب الـ Esports والفريمات العالية",
        "label_en": "Competitive Esports & High-Hz Gaming",
        "weights": {
            "cpu_score": 0.19,
            "gpu_compute_score": 0.24,
            "vram_score": 0.05,
            "power_therm_score": 0.10,
            "display_gaming_score": 0.20,
            "display_creator_score": 0.01,
            "battery_score": 0.01,
            "portability_score": 0.01,
            "upgradeability_score": 0.03,
            "build_quality_score": 0.02,
            "ergonomics_score": 0.02,
            "connectivity_score": 0.02,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "min_refresh_hz": 144,
            "min_ram_gb": 16,
        },
    },
    "gaming_aaa": {
        "label_ar": "ألعاب الـ AAA الثقيلة والجرافيك الفائق",
        "label_en": "Heavy AAA & Ray-Traced Gaming",
        "weights": {
            "cpu_score": 0.14,
            "gpu_compute_score": 0.30,
            "vram_score": 0.16,
            "power_therm_score": 0.13,
            "display_gaming_score": 0.08,
            "display_creator_score": 0.05,
            "battery_score": 0.00,
            "portability_score": 0.00,
            "upgradeability_score": 0.03,
            "build_quality_score": 0.02,
            "ergonomics_score": 0.01,
            "connectivity_score": 0.00,
            "effective_price_egp": 0.08,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "min_vram_gb": 6,
            "min_ram_gb": 16,
        },
    },
    "gaming_budget": {
        "label_ar": "الألعاب الاقتصادية (أفضل أداء مقابل سعر)",
        "label_en": "Budget Gaming (Max Value per EGP)",
        "weights": {
            "cpu_score": 0.14,
            "gpu_compute_score": 0.26,
            "vram_score": 0.08,
            "power_therm_score": 0.09,
            "display_gaming_score": 0.09,
            "display_creator_score": 0.01,
            "battery_score": 0.01,
            "portability_score": 0.01,
            "upgradeability_score": 0.08,
            "build_quality_score": 0.02,
            "ergonomics_score": 0.01,
            "connectivity_score": 0.00,
            "effective_price_egp": 0.20,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "min_ram_gb": 8,
        },
    },
    "creative": {
        "label_ar": "صناعة المحتوى والتصميم والمونتاج (عام)",
        "label_en": "Content Creation & Design (Main)",
        "weights": {
            "cpu_score": 0.19,
            "gpu_compute_score": 0.18,
            "vram_score": 0.08,
            "power_therm_score": 0.08,
            "display_gaming_score": 0.01,
            "display_creator_score": 0.22,
            "battery_score": 0.02,
            "portability_score": 0.02,
            "upgradeability_score": 0.04,
            "build_quality_score": 0.03,
            "ergonomics_score": 0.01,
            "connectivity_score": 0.02,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 16,
            "require_creator_display": True,
        },
    },
    "creative_video": {
        "label_ar": "المونتاج وتصحيح الألوان وإنتاج الفيديو",
        "label_en": "Video Editing & Color Grading",
        "weights": {
            "cpu_score": 0.22,
            "gpu_compute_score": 0.18,
            "vram_score": 0.08,
            "power_therm_score": 0.09,
            "display_gaming_score": 0.00,
            "display_creator_score": 0.20,
            "battery_score": 0.01,
            "portability_score": 0.01,
            "upgradeability_score": 0.05,
            "build_quality_score": 0.02,
            "ergonomics_score": 0.01,
            "connectivity_score": 0.05,
            "effective_price_egp": 0.08,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "min_ram_gb": 16,
            "require_creator_display": True,
        },
    },
    "creative_2d_photo": {
        "label_ar": "التصميم الجرافيكي وتعديل الصور (2D & UI/UX)",
        "label_en": "2D Graphic Design, Photography & UI/UX",
        "weights": {
            "cpu_score": 0.18,
            "gpu_compute_score": 0.08,
            "vram_score": 0.03,
            "power_therm_score": 0.04,
            "display_gaming_score": 0.00,
            "display_creator_score": 0.30,
            "battery_score": 0.07,
            "portability_score": 0.08,
            "upgradeability_score": 0.03,
            "build_quality_score": 0.04,
            "ergonomics_score": 0.02,
            "connectivity_score": 0.03,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 16,
            "require_creator_display": True,
        },
    },
    "creative_3d_cad_gamedev": {
        "label_ar": "التصميم ثلاثي الأبعاد والـ CAD وتطوير الألعاب",
        "label_en": "3D Rendering, CAD/BIM & Game Development",
        "weights": {
            "cpu_score": 0.19,
            "gpu_compute_score": 0.26,
            "vram_score": 0.15,
            "power_therm_score": 0.12,
            "display_gaming_score": 0.03,
            "display_creator_score": 0.08,
            "battery_score": 0.00,
            "portability_score": 0.00,
            "upgradeability_score": 0.05,
            "build_quality_score": 0.02,
            "ergonomics_score": 0.00,
            "connectivity_score": 0.02,
            "effective_price_egp": 0.08,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "min_vram_gb": 6,
            "min_ram_gb": 16,
        },
    },
    "tech": {
        "label_ar": "البرمجة والتكنولوجيا وعلوم الحاسب (عام)",
        "label_en": "Software Engineering & Tech (Main)",
        "weights": {
            "cpu_score": 0.24,
            "gpu_compute_score": 0.10,
            "vram_score": 0.05,
            "power_therm_score": 0.07,
            "display_gaming_score": 0.00,
            "display_creator_score": 0.06,
            "battery_score": 0.08,
            "portability_score": 0.06,
            "upgradeability_score": 0.11,
            "build_quality_score": 0.05,
            "ergonomics_score": 0.04,
            "connectivity_score": 0.04,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 16,
            "min_cpu_cores": 6,
        },
    },
    "tech_ai_ml": {
        "label_ar": "الذكاء الاصطناعي وتعلم الآلة وعلم البيانات",
        "label_en": "AI / ML Engineering & CUDA Compute",
        "weights": {
            "cpu_score": 0.16,
            "gpu_compute_score": 0.24,
            "vram_score": 0.18,
            "power_therm_score": 0.10,
            "display_gaming_score": 0.00,
            "display_creator_score": 0.01,
            "battery_score": 0.01,
            "portability_score": 0.01,
            "upgradeability_score": 0.10,
            "build_quality_score": 0.03,
            "ergonomics_score": 0.02,
            "connectivity_score": 0.04,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "require_nvidia": True,
            "min_vram_gb": 6,
            "min_ram_gb": 16,
        },
    },
    "tech_web_mobile": {
        "label_ar": "تطوير الويب والموبايل والباك إند",
        "label_en": "Full-Stack Web & Mobile Development",
        "weights": {
            "cpu_score": 0.26,
            "gpu_compute_score": 0.03,
            "vram_score": 0.00,
            "power_therm_score": 0.06,
            "display_gaming_score": 0.00,
            "display_creator_score": 0.08,
            "battery_score": 0.12,
            "portability_score": 0.08,
            "upgradeability_score": 0.12,
            "build_quality_score": 0.05,
            "ergonomics_score": 0.06,
            "connectivity_score": 0.04,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 16,
            "min_cpu_cores": 6,
        },
    },
    "tech_cyber_vms": {
        "label_ar": "الأمن السيبراني والشبكات والأنظمة الافتراضية",
        "label_en": "Cybersecurity, DevOps & Heavy VMs",
        "weights": {
            "cpu_score": 0.25,
            "gpu_compute_score": 0.04,
            "vram_score": 0.02,
            "power_therm_score": 0.08,
            "display_gaming_score": 0.00,
            "display_creator_score": 0.04,
            "battery_score": 0.07,
            "portability_score": 0.05,
            "upgradeability_score": 0.18,
            "build_quality_score": 0.05,
            "ergonomics_score": 0.04,
            "connectivity_score": 0.08,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 16,
            "min_cpu_cores": 6,
        },
    },
    "balanced": {
        "label_ar": "استخدام شامل متوازن (أفضل قيمة)",
        "label_en": "Balanced All-Rounder (Main)",
        "weights": {
            "cpu_score": 0.18,
            "gpu_compute_score": 0.12,
            "vram_score": 0.03,
            "power_therm_score": 0.06,
            "display_gaming_score": 0.03,
            "display_creator_score": 0.10,
            "battery_score": 0.10,
            "portability_score": 0.08,
            "upgradeability_score": 0.06,
            "build_quality_score": 0.06,
            "ergonomics_score": 0.04,
            "connectivity_score": 0.04,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 8,
        },
    },
    "daily_student": {
        "label_ar": "الطلاب والجامعة والمحاضرات",
        "label_en": "University Student & Campus Mobility",
        "weights": {
            "cpu_score": 0.15,
            "gpu_compute_score": 0.02,
            "vram_score": 0.00,
            "power_therm_score": 0.04,
            "display_gaming_score": 0.00,
            "display_creator_score": 0.07,
            "battery_score": 0.22,
            "portability_score": 0.16,
            "upgradeability_score": 0.05,
            "build_quality_score": 0.08,
            "ergonomics_score": 0.03,
            "connectivity_score": 0.02,
            "effective_price_egp": 0.16,
        },
        "implicit_gates": {
            "min_ram_gb": 8,
            "max_weight_kg": 2.20,
        },
    },
    "daily_business": {
        "label_ar": "البيزنس والتنقل المستمر والاجتماعات",
        "label_en": "Executive Business & Ultraportable Travel",
        "weights": {
            "cpu_score": 0.14,
            "gpu_compute_score": 0.01,
            "vram_score": 0.00,
            "power_therm_score": 0.04,
            "display_gaming_score": 0.00,
            "display_creator_score": 0.09,
            "battery_score": 0.20,
            "portability_score": 0.22,
            "upgradeability_score": 0.02,
            "build_quality_score": 0.10,
            "ergonomics_score": 0.06,
            "connectivity_score": 0.04,
            "effective_price_egp": 0.08,
        },
        "implicit_gates": {
            "min_ram_gb": 8,
            "max_weight_kg": 1.75,
        },
    },
    "daily_office": {
        "label_ar": "العمل المكتبي والمحاسبة والأعمال اليومية",
        "label_en": "Office Productivity & Daily Work",
        "weights": {
            "cpu_score": 0.18,
            "gpu_compute_score": 0.01,
            "vram_score": 0.00,
            "power_therm_score": 0.04,
            "display_gaming_score": 0.00,
            "display_creator_score": 0.09,
            "battery_score": 0.15,
            "portability_score": 0.10,
            "upgradeability_score": 0.05,
            "build_quality_score": 0.07,
            "ergonomics_score": 0.09,
            "connectivity_score": 0.04,
            "effective_price_egp": 0.18,
        },
        "implicit_gates": {
            "min_ram_gb": 8,
            "max_weight_kg": 2.35,
        },
    },
}


def _resolve_persona_key(persona: str | None) -> str:
    """Resolve persona name or legacy alias to a valid 16-persona key."""
    if not persona:
        return "balanced"
    if persona in PERSONA_CONFIGS:
        return persona
    mapped = LEGACY_PERSONA_ALIASES.get(persona)
    if mapped and mapped in PERSONA_CONFIGS:
        return mapped
    return "balanced"

def resolve_persona_key(persona: str | None) -> str:
    """Resolve any 16-persona key or 5 legacy alias into a valid PERSONA_CONFIGS key."""
    key = str(persona or PersonaType.BALANCED).lower().strip()
    key = LEGACY_PERSONA_ALIASES.get(key, key)
    return key if key in PERSONA_CONFIGS else PersonaType.BALANCED


def parse_user_text_prompt(prompt: str | None) -> dict[str, Any]:
    """Turn optional Arabic/English user text into hard constraints and criteria weight boosts."""
    if not prompt or not str(prompt).strip():
        return {"extracted_filters": {}, "weight_boosts": {}}

    txt = str(prompt).lower()
    extracted_filters: dict[str, Any] = {}
    weight_boosts: dict[str, float] = {}

    # --- A. Extract Explicit Hardware Constraints from Text ---
    for ram_val in (64, 32, 24, 16):
        if re.search(
            rf"(?<!\d){ram_val}\s*(?:gb|جيجا)(?![a-z\d])"
            rf"|(?:رامات|راماته|رام|ram)\s*[:=]?\s*{ram_val}(?!\d)"
            rf"|(?<!\d){ram_val}\s*(?:رامات|رام|ram)(?![a-z\d])",
            txt,
        ):
            extracted_filters["min_ram_gb"] = ram_val
            break

    if re.search(
        r"(?<!\d)(?:2\s*tb|2000\s*gb|2\s*تيرا)(?![a-z\d])"
        r"|(?:هارد|تخزين|مساحة|ssd)\s*[:=]?\s*2\s*(?:tb|تيرا)(?![a-z\d])",
        txt,
    ):
        extracted_filters["min_storage_gb"] = 2048
    elif re.search(
        r"(?<!\d)(?:1\s*tb|1000\s*gb|1024\s*gb|1\s*تيرا)(?![a-z\d])"
        r"|(?:^|[\s,،.\-+/()])(?:تيرا|هارد\s*تيرا)(?=$|[\s,،.\-+/()])",
        txt,
    ):
        extracted_filters["min_storage_gb"] = 1024
    elif re.search(
        r"(?<!\d)(?:512\s*gb|512\s*جيجا)(?![a-z\d])"
        r"|(?:هارد|تخزين|مساحة|ssd)\s*[:=]?\s*512(?!\d)",
        txt,
    ):
        extracted_filters["min_storage_gb"] = 512

    if any(k in txt for k in ["oled", "اوليد", "أوليد"]):
        extracted_filters["require_oled"] = True
    if any(k in txt for k in ["touch", "تاتش", "لمس", "x360", "flip", "2-in-1"]):
        extracted_filters["require_touchscreen"] = True

    # --- B. Extract Dynamic Weight Boosts from Intent Keywords ---
    if any(k in txt for k in ["بطاريه", "بطارية", "شحن", "battery"]):
        weight_boosts["battery_score"] = weight_boosts.get("battery_score", 0.0) + 0.14
    if any(k in txt for k in ["خفيف", "تنقل", "سفر", "مواصلات", "محاضرات", "lightweight", "portable", "travel", "thin"]):
        weight_boosts["portability_score"] = weight_boosts.get("portability_score", 0.0) + 0.12
        weight_boosts["battery_score"] = weight_boosts.get("battery_score", 0.0) + 0.06

    if any(k in txt for k in ["شاشه", "شاشة", "الوان", "ألوان", "دقة", "سطوع", "مونتاج", "جرافيك", "display", "screen", "color", "srgb", "oled", "hdr"]):
        weight_boosts["display_creator_score"] = weight_boosts.get("display_creator_score", 0.0) + 0.14

    if any(k in txt for k in ["كارت شاشه", "كارت شاشة", "العاب", "ألعاب", "فريمات", "رندر", "جيمز", "gaming", "fps", "rtx", "gpu", "render", "3d"]):
        weight_boosts["gpu_compute_score"] = weight_boosts.get("gpu_compute_score", 0.0) + 0.12
        weight_boosts["vram_score"] = weight_boosts.get("vram_score", 0.0) + 0.06
        weight_boosts["power_therm_score"] = weight_boosts.get("power_therm_score", 0.0) + 0.05

    if any(k in txt for k in ["معالج", "بروسيسور", "برمجه", "برمجة", "محاكاة", "داتا", "كود", "cpu", "processor", "coding", "docker", "vm", "multitask"]):
        weight_boosts["cpu_score"] = weight_boosts.get("cpu_score", 0.0) + 0.14

    if any(k in txt for k in ["تبريد", "حراره", "حرارة", "مراوح", "سخونة", "باور", "cooling", "thermal", "heat", "tgp", "watt"]):
        weight_boosts["power_therm_score"] = weight_boosts.get("power_therm_score", 0.0) + 0.14

    if any(k in txt for k in ["تطوير", "ترقيه", "ترقية", "يعيش", "مستقبل", "رامات بتزيد", "upgrade", "future", "slots", "longevity", "expand"]):
        weight_boosts["upgradeability_score"] = weight_boosts.get("upgradeability_score", 0.0) + 0.12
        weight_boosts["build_quality_score"] = weight_boosts.get("build_quality_score", 0.0) + 0.05

    if any(k in txt for k in ["كيبورد", "كاميرا", "صوت", "اجتماعات", "زووم", "بصمه", "بصمة", "keyboard", "webcam", "camera", "mic", "audio", "zoom"]):
        weight_boosts["ergonomics_score"] = weight_boosts.get("ergonomics_score", 0.0) + 0.12

    if any(k in txt for k in ["منافذ", "تايب سي", "ثندربولت", "لان", "شاشات خارجية", "ports", "thunderbolt", "usb-c", "hdmi", "ethernet", "lan"]):
        weight_boosts["connectivity_score"] = weight_boosts.get("connectivity_score", 0.0) + 0.12

    if any(k in txt for k in ["ارخص", "أرخص", "توفير", "سعر", "اقتصادي", "على قد الايد", "cheap", "budget", "value", "save", "affordable"]):
        weight_boosts["effective_price_egp"] = weight_boosts.get("effective_price_egp", 0.0) + 0.14

    return {
        "extracted_filters": extracted_filters,
        "weight_boosts": weight_boosts,
    }


def get_persona_db_query_spec(persona: str, max_budget_egp: float) -> dict[str, Any]:
    """Return baseline filter spec with low-budget relaxation for backend queries."""
    p_key = resolve_persona_key(persona)
    gates = copy.deepcopy(PERSONA_CONFIGS[p_key]["implicit_gates"])
    if max_budget_egp < 35000:
        if gates.get("min_ram_gb", 8) > 8:
            gates["min_ram_gb"] = 8
        if max_budget_egp < 30000 and gates.get("require_dgpu"):
            gates["require_dgpu"] = False
            gates.pop("require_nvidia", None)
            gates.pop("min_refresh_hz", None)
            gates.pop("min_vram_gb", None)

    return {
        "in_stock_active": True,
        "max_price_egp": max_budget_egp,
        "persona_gates": gates,
    }
