"""Pure TOPSIS, persona weighting, bilingual prompt parsing, and semantic scoring domain logic.

Zero external I/O, database, HTTP framework, or model loading dependencies.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.domain.metrics.scoring import (
    DEFAULT_COMMUNITY_NLP_SCORE,
    calculate_calibrated_value_score,
)

# =============================================================================
# 1. PERSONA WEIGHT CONFIGURATIONS (14-Column TOPSIS Matrix, 16 Personas)
# =============================================================================
# The 14 TOPSIS columns in order:
# [0]  cpu_score             (Benefit +)
# [1]  gpu_compute_score     (Benefit +)
# [2]  vram_score            (Benefit +)
# [3]  power_therm_score     (Benefit +)
# [4]  display_gaming_score  (Benefit +)
# [5]  display_creator_score (Benefit +)
# [6]  battery_score         (Benefit +)
# [7]  portability_score     (Benefit +)
# [8]  upgradeability_score  (Benefit +)
# [9]  build_quality_score   (Benefit +)
# [10] ergonomics_score      (Benefit +)
# [11] connectivity_score    (Benefit +)
# [12] community_nlp_score   (Benefit +)
# [13] effective_price_egp   (Cost    -)

DEFAULT_COMMUNITY_NLP_WEIGHT = 0.08

TOPSIS_CRITERIA_KEYS: List[str] = [
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
IS_BENEFIT_CRITERION: List[bool] = [True] * 13 + [False]

# Reference bilingual anchor descriptions for Semantic Weight Boosting
CRITERIA_SEMANTIC_ANCHORS: Dict[str, str] = {
    "cpu_score": "معالج قوي بروسيسور سريع للبرمجة والملتي تاسكينج والمحاكاة والداتا fast CPU processor heavy coding multitasking virtualization",
    "gpu_score": "كارت شاشة قوي للألعاب الثقيلة وفريمات عالية وريندر وجرافيك 3D powerful gaming GPU high FPS RTX rendering",
    "power_therm_score": "تبريد ممتاز ميسخنش في الصيف مراوح قوية باور عالي بدون اختناق حراري excellent cooling thermals runs cool no thermal throttling full TGP",
    "display_score": "شاشة اوليد ألوان دقيقة مونتاج وتصميم سطوع عالي 100% sRGB OLED display screen accurate colors brightness",
    "mobility_score": "بطارية تقعد وقت طويل وزن خفيف للتنقل والسفر والجامعة والمحاضرات long battery life lightweight portable thin travel",
    "longevity_score": "قابل للتطوير وزيادة الرامات والهارد ومفصلات وشاسيه متين يعيش للمستقبل upgradeable RAM SSD slots durable metal chassis sturdy hinges",
    "ergonomics_score": "كيبورد مريحة في الكتابة كاميرا نقية للاجتماعات وصوت عالي وبصمة comfortable backlit keyboard good webcam microphone speakers fingerprint",
    "connectivity_score": "منافذ كتير تايب سي ثندربولت وكابل نت وشاشات خارجية thunderbolt USB-C PD HDMI ethernet LAN ports",
}

LEGACY_PERSONA_ALIASES: Dict[str, str] = {
    "ai_and_game_dev": "tech_ai_ml",
    "programming": "tech_web_mobile",
    "content_creation": "creative",
    "student_and_office": "daily_student",
    "business_and_mobility": "daily_business",
}

PERSONA_CONFIGS: Dict[str, Dict[str, Any]] = {
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


def _resolve_persona_key(persona: Optional[str]) -> str:
    """Resolve persona name or legacy alias to a valid 16-persona key."""
    if not persona:
        return "balanced"
    if persona in PERSONA_CONFIGS:
        return persona
    mapped = LEGACY_PERSONA_ALIASES.get(persona)
    if mapped and mapped in PERSONA_CONFIGS:
        return mapped
    return "balanced"


# =============================================================================
# 2. BILINGUAL (AR/EN) TEXT PROMPT PARSER (Extracts Filters + Weight Boosts)
# =============================================================================
def parse_user_text_prompt(prompt: Optional[str]) -> Dict[str, Any]:
    """Turn optional Arabic/English user text into hard constraints and criteria weight boosts."""
    if not prompt or not str(prompt).strip():
        return {"extracted_filters": {}, "weight_boosts": {}}

    txt = str(prompt).lower()
    extracted_filters: Dict[str, Any] = {}
    weight_boosts: Dict[str, float] = {}

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


def get_persona_db_query_spec(persona: str, max_budget_egp: float) -> Dict[str, Any]:
    """Return baseline filter spec with low-budget relaxation for backend queries."""
    p_key = _resolve_persona_key(persona)
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


def _run_topsis_vector(
    decision_matrix: np.ndarray,
    weights_vec: np.ndarray,
    is_benefit_vec: List[bool],
) -> np.ndarray:
    """Execute standard Vector-Normalized TOPSIS on an (M x N) NumPy matrix."""
    m_rows, n_cols = decision_matrix.shape
    if m_rows == 0:
        return np.array([], dtype=float)
    if m_rows == 1:
        return np.array([100.0], dtype=float)

    col_norms = np.linalg.norm(decision_matrix, axis=0)
    col_norms[col_norms == 0.0] = 1.0
    r_mat = decision_matrix / col_norms

    w_norm = weights_vec / np.sum(weights_vec)
    v_mat = r_mat * w_norm

    ideal_best = np.zeros(n_cols, dtype=float)
    ideal_worst = np.zeros(n_cols, dtype=float)
    for j in range(n_cols):
        if is_benefit_vec[j]:
            ideal_best[j] = np.max(v_mat[:, j])
            ideal_worst[j] = np.min(v_mat[:, j])
        else:
            ideal_best[j] = np.min(v_mat[:, j])
            ideal_worst[j] = np.max(v_mat[:, j])

    d_pos = np.linalg.norm(v_mat - ideal_best, axis=1)
    d_neg = np.linalg.norm(v_mat - ideal_worst, axis=1)

    denom = d_pos + d_neg
    closeness = np.where(denom > 1e-12, (d_neg / denom) * 100.0, 50.0)
    return np.round(closeness, 2)


def _build_why_recommended(laptop: Dict[str, Any], persona: str) -> Dict[str, List[str]]:
    s = laptop["specs"]
    dm = laptop["derived_metrics"]
    reasons_ar: List[str] = []
    reasons_en: List[str] = []

    cpu_name = s["cpu"].get("full_name") or s["cpu"].get("model")
    cores = s["cpu"].get("cores")
    boost = s["cpu"].get("clock_boost_ghz")
    gpu_model = s["gpu"].get("model")
    is_igpu = s["gpu"].get("integrated")
    tgp = dm["silicon"].get("inferred_tgp_w")
    vram = s["gpu"].get("vram_gb")
    ram_gb = s["memory"].get("capacity_gb")
    mem_type = s["memory"].get("memory_type")
    ssd_gb = s["storage"].get("capacity_gb")
    ssd_str = f"{ssd_gb // 1024}TB" if (ssd_gb and ssd_gb >= 1024) else f"{ssd_gb}GB"

    if not is_igpu and gpu_model:
        reasons_ar.append(f"كارت شاشة {gpu_model} ({vram}GB) بقدرة {int(tgp)}W ومعالج {cpu_name}")
        reasons_en.append(f"{gpu_model} ({vram}GB, {int(tgp)}W TGP) paired with {cpu_name}")
    else:
        reasons_ar.append(f"معالج {cpu_name} ({cores} أنوية حتى {boost}GHz) مع رام {ram_gb}GB {mem_type}")
        reasons_en.append(f"{cpu_name} ({cores}C, up to {boost}GHz) with {ram_gb}GB {mem_type} RAM")

    disp_size = s["display"].get("size_inches")
    panel = dm["display"].get("panel_technology")
    hz = dm["display"].get("refresh_rate_hz")
    gamut = dm["display"].get("color_gamut_tier", "").split(" (")[0]
    reasons_ar.append(f"شاشة {disp_size} بوصة {panel} بتردد {hz}Hz وتغطية ألوان {gamut}")
    reasons_en.append(f"{disp_size}-inch {panel} {hz}Hz display ({gamut})")

    if persona in [
        "daily_student",
        "daily_business",
        "daily_office",
        "student_and_office",
        "business_and_mobility",
    ]:
        w_kg = dm["mobility"].get("weight_kg")
        b_hrs = dm["mobility"].get("battery_hours_estimate")
        reasons_ar.append(f"وزن خفيف {w_kg} كجم وبطارية تدوم حوالي {b_hrs} ساعات مع تخزين {ssd_str} SSD")
        reasons_en.append(f"Lightweight {w_kg} kg chassis with ~{b_hrs}h battery life & {ssd_str} SSD")
    else:
        m2_slots = dm["longevity"].get("total_m2_slots")
        max_r = dm["longevity"].get("max_ram_gb")
        reasons_ar.append(f"رام {ram_gb}GB {mem_type} (تقبل حتى {max_r}GB) وتخزين {ssd_str} ({m2_slots} فتحات M.2)")
        reasons_en.append(f"{ram_gb}GB {mem_type} RAM (up to {max_r}GB) & {ssd_str} SSD ({m2_slots}x M.2 slots)")

    price = dm["topsis_inputs"].get("effective_price_egp")
    store = laptop.get("cheapest_store")
    spread = laptop.get("price_spread_egp") or 0
    if spread >= 1000:
        reasons_ar.append(f"أفضل سعر متاح لدى {store} ({price:,.0f} ج.م) بتوفير {spread:,.0f} ج.م عن أعلى متجر")
        reasons_en.append(f"Best price at {store} ({price:,.0f} EGP), saving {spread:,.0f} EGP across stores")
    elif price:
        reasons_ar.append(f"متاح بسعر {price:,.0f} ج.م لدى {store}")
        reasons_en.append(f"Available at {price:,.0f} EGP via {store}")

    return {"ar": reasons_ar, "en": reasons_en}


def _is_nvidia_gpu(laptop: Dict[str, Any]) -> bool:
    """Detect whether a laptop contains an NVIDIA discrete GPU (CUDA-capable)."""
    gpu = laptop.get("specs", {}).get("gpu", {})
    if gpu.get("integrated", True):
        return False
    mfr = str(gpu.get("manufacturer") or gpu.get("brand") or "").lower()
    model = str(gpu.get("model") or "").lower()
    raw = str(gpu.get("raw_spec") or "").lower()
    title = str(laptop.get("title") or "").lower()
    if "nvidia" in mfr or "nvidia" in model:
        return True
    if any(tok in model for tok in ("geforce", "rtx", "gtx", "quadro")):
        return True
    if "nvidia" in raw and ("rtx" in raw or "geforce" in raw):
        return True
    if any(tok in title for tok in ("rtx ", "rtx4", "rtx5", "rtx3", "rtx2", "gtx ", "geforce")):
        return True
    return False


_LEGACY_WEIGHT_EXPANSION: Dict[str, Tuple[Tuple[str, float], ...]] = {
    "gpu_score": (("gpu_compute_score", 0.72), ("vram_score", 0.28)),
    "display_score": (("display_gaming_score", 0.45), ("display_creator_score", 0.55)),
    "mobility_score": (("battery_score", 0.50), ("portability_score", 0.50)),
    "longevity_score": (("upgradeability_score", 0.65), ("build_quality_score", 0.35)),
}


def _apply_weight_overrides(
    weights_dict: Dict[str, float],
    overrides: Dict[str, float],
    additive: bool,
) -> None:
    """Apply overrides onto 14-column weights, expanding any legacy 10-column keys safely."""
    for k, v in overrides.items():
        if v is None:
            continue
        fval = float(v)
        if k in weights_dict:
            weights_dict[k] = (weights_dict[k] + fval) if additive else fval
        elif k in _LEGACY_WEIGHT_EXPANSION:
            for sub_k, share in _LEGACY_WEIGHT_EXPANSION[k]:
                if sub_k in weights_dict:
                    delta = fval * share
                    weights_dict[sub_k] = (weights_dict[sub_k] + delta) if additive else delta


def _extract_matrix_cell(
    ti: Dict[str, Any],
    col_key: str,
    cid: str,
    adjusted_nlp_scores: Optional[Dict[str, float]],
) -> float:
    """Safely extract a 14-column numeric criterion with backward-compatible fallbacks."""
    if col_key == "community_nlp_score":
        if adjusted_nlp_scores and cid in adjusted_nlp_scores and adjusted_nlp_scores[cid] is not None:
            val = float(adjusted_nlp_scores[cid])
        elif ti.get("community_nlp_score") is not None:
            val = float(ti["community_nlp_score"])
        else:
            val = DEFAULT_COMMUNITY_NLP_SCORE
        return val if math.isfinite(val) else DEFAULT_COMMUNITY_NLP_SCORE

    raw_val = ti.get(col_key)
    if raw_val is None:
        fallback_map = {
            "gpu_compute_score": ti.get("gpu_score", 18.0),
            "vram_score": 15.0,
            "display_gaming_score": ti.get("display_score", 50.0),
            "display_creator_score": ti.get("display_score", 50.0),
            "battery_score": ti.get("mobility_score", 50.0),
            "portability_score": ti.get("mobility_score", 50.0),
            "upgradeability_score": ti.get("longevity_score", 50.0),
            "build_quality_score": ti.get("longevity_score", 60.0),
        }
        raw_val = fallback_map.get(col_key, 50.0)
    val = float(raw_val)
    return val if math.isfinite(val) else (DEFAULT_COMMUNITY_NLP_SCORE if col_key == "community_nlp_score" else 50.0)


def _compute_persona_value_score(
    laptop: Dict[str, Any],
    hw_row_13: np.ndarray,
    hw_weights_13: np.ndarray,
    p_key: str,
    eff_price: Optional[float],
) -> float:
    """Compute smoothly calibrated persona value score from persona hardware_fit and price."""
    if not eff_price or eff_price < 10000:
        return 50.0
    ps_entry = laptop.get("derived_metrics", {}).get("persona_scores", {}).get(p_key, {})
    persona_hw_fit = ps_entry.get("hardware_fit")
    if persona_hw_fit is None:
        w_sum = float(np.sum(hw_weights_13))
        if w_sum > 1e-12:
            persona_hw_fit = float(np.dot(hw_row_13, hw_weights_13) / w_sum)
        else:
            persona_hw_fit = float(np.mean(hw_row_13))
    return calculate_calibrated_value_score(max(1.0, float(persona_hw_fit)), eff_price)


def compute_nlp_dynamic_weight(net_sims: List[float]) -> Tuple[float, float]:
    """Map net_sim spread (mean top-5 minus median rest) smoothly to [0.10, 0.25]."""
    if not net_sims:
        return 0.10, 0.0
    sorted_sims = sorted(net_sims, reverse=True)
    if len(sorted_sims) > 5:
        spread = max(0.0, float(np.mean(sorted_sims[:5]) - np.median(sorted_sims[5:])))
    else:
        spread = max(0.0, float(sorted_sims[0] - np.median(sorted_sims)))
    ratio = max(0.0, min(1.0, (spread - 0.08) / (0.26 - 0.08)))
    dyn_weight = round(0.10 + ratio * (0.25 - 0.10), 4)
    return dyn_weight, round(spread, 4)


def score_dual_review_vectors_detailed(
    pro_res: Optional[Dict[str, Any]],
    con_res: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute net Dual-Vector review adjustments plus dynamic signal-spread weighting."""
    pro_sim: Dict[str, float] = {}
    con_sim: Dict[str, float] = {}
    base_scores: Dict[str, float] = {}
    cids_map: Dict[str, List[str]] = {}

    if pro_res and pro_res.get("metadatas") and pro_res.get("distances"):
        for meta, dist in zip(pro_res["metadatas"][0], pro_res["distances"][0]):
            ckey = meta["chassis_key"]
            pro_sim[ckey] = max(0.0, 1.0 - float(dist))
            base_scores[ckey] = float(meta.get("community_nlp_score", DEFAULT_COMMUNITY_NLP_SCORE))
            cids_map[ckey] = [c for c in meta.get("matched_canonical_ids", "").split(",") if c]

    if con_res and con_res.get("metadatas") and con_res.get("distances"):
        for meta, dist in zip(con_res["metadatas"][0], con_res["distances"][0]):
            ckey = meta["chassis_key"]
            con_sim[ckey] = max(0.0, 1.0 - float(dist))
            base_scores.setdefault(
                ckey, float(meta.get("community_nlp_score", DEFAULT_COMMUNITY_NLP_SCORE))
            )
            if ckey not in cids_map:
                cids_map[ckey] = [c for c in meta.get("matched_canonical_ids", "").split(",") if c]

    adjusted_nlp_scores: Dict[str, float] = {}
    net_sims: List[float] = []
    for ckey, base_s in base_scores.items():
        net_sim = pro_sim.get(ckey, 0.0) - 0.75 * con_sim.get(ckey, 0.0)
        net_sims.append(net_sim)
        adj = max(35.0, min(98.0, round(base_s + net_sim * 32.0, 2)))
        for cid in cids_map.get(ckey, []):
            adjusted_nlp_scores[cid] = adj

    dyn_weight, signal_spread = compute_nlp_dynamic_weight(net_sims)
    return {
        "adjusted_nlp_scores": adjusted_nlp_scores,
        "nlp_dynamic_weight": dyn_weight,
        "signal_spread": signal_spread,
    }


def score_dual_review_vectors(
    pro_res: Optional[Dict[str, Any]],
    con_res: Optional[Dict[str, Any]],
) -> Dict[str, float]:
    """Compute net Dual-Vector review similarity adjustment per canonical ID."""
    return score_dual_review_vectors_detailed(pro_res, con_res)["adjusted_nlp_scores"]


def compute_semantic_weight_boosts(
    anchor_keys: List[str],
    anchor_matrix: Optional[np.ndarray],
    query_vec: np.ndarray,
) -> Dict[str, float]:
    """Compute cosine-similarity TOPSIS criteria boosts against normalized semantic anchors."""
    semantic_boosts: Dict[str, float] = {}
    if anchor_matrix is None:
        return semantic_boosts
    sims = np.dot(anchor_matrix, query_vec)
    for idx, sim_val in enumerate(sims):
        if sim_val >= 0.48:
            key = anchor_keys[idx]
            semantic_boosts[key] = round(float((sim_val - 0.45) * 0.35), 3)
    return semantic_boosts


def build_budget_too_low_fallback(working_laptops: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    """Return cheapest in-stock alternatives when no laptop matches the requested budget window."""
    active_all = [
        l
        for l in working_laptops
        if l.get("derived_metrics", {}).get("topsis_inputs", {}).get("in_stock_active")
    ]
    active_all.sort(
        key=lambda x: x["derived_metrics"]["topsis_inputs"].get("effective_price_egp") or 999999
    )
    return [
        {
            "canonical_id": l["canonical_id"],
            "title": l.get("title"),
            "effective_price_egp": l["derived_metrics"]["topsis_inputs"].get("effective_price_egp"),
            "cheapest_store": l.get("cheapest_store"),
        }
        for l in active_all[:limit]
    ]


def rank_laptops_topsis(
    laptops: List[Dict[str, Any]],
    max_budget_egp: float = 300000.0,
    min_budget_egp: Optional[float] = None,
    persona: str = "balanced",
    user_text_prompt: Optional[str] = None,
    min_ram_gb: Optional[int] = None,
    min_storage_gb: Optional[int] = None,
    require_dgpu: Optional[bool] = None,
    brand_filter: Optional[List[str]] = None,
    custom_weights: Optional[Dict[str, float]] = None,
    nlp_dynamic_weight: Optional[float] = None,
    adjusted_nlp_scores: Optional[Dict[str, float]] = None,
    apply_smart_60pct_floor: bool = True,
    min_floor_candidates: int = 5,
    top_k: int = 10,
) -> Dict[str, Any]:
    """Run budget-scoped 14-column TOPSIS ranking with implicit persona gates and smart fallback."""
    p_key = _resolve_persona_key(persona)
    p_cfg = PERSONA_CONFIGS[p_key]

    parsed_prompt = parse_user_text_prompt(user_text_prompt)
    ext_filters = parsed_prompt["extracted_filters"]
    w_boosts = parsed_prompt["weight_boosts"]

    final_weights_dict = copy.deepcopy(p_cfg["weights"])
    final_weights_dict.setdefault("community_nlp_score", DEFAULT_COMMUNITY_NLP_WEIGHT)
    if nlp_dynamic_weight is not None:
        final_weights_dict["community_nlp_score"] = float(nlp_dynamic_weight)
    if custom_weights:
        _apply_weight_overrides(final_weights_dict, custom_weights, additive=False)
    if w_boosts:
        _apply_weight_overrides(final_weights_dict, w_boosts, additive=True)

    w_sum = sum(final_weights_dict.values()) or 1.0
    final_weights_dict = {k: round(v / w_sum, 4) for k, v in final_weights_dict.items()}
    weights_vec = np.array([final_weights_dict[k] for k in TOPSIS_CRITERIA_KEYS], dtype=float)
    hw_weights_13 = weights_vec[:13]

    eff_min_ram = min_ram_gb or ext_filters.get("min_ram_gb")
    eff_min_sto = min_storage_gb or ext_filters.get("min_storage_gb")
    brands_norm = {b.lower() for b in brand_filter} if brand_filter else None

    base_pool: List[Dict[str, Any]] = []
    for lap in laptops:
        ti = lap.get("derived_metrics", {}).get("topsis_inputs", {})
        if not ti.get("in_stock_active", False):
            continue
        price = ti.get("effective_price_egp")
        if price is None or price > max_budget_egp:
            continue
        if min_budget_egp is not None and price < min_budget_egp:
            continue
        if brands_norm and str(lap.get("brand") or "").lower() not in brands_norm:
            continue
        if eff_min_ram and (lap["specs"]["memory"].get("capacity_gb") or 0) < eff_min_ram:
            continue
        if eff_min_sto and (lap["specs"]["storage"].get("capacity_gb") or 0) < eff_min_sto:
            continue
        if require_dgpu is True and lap["specs"]["gpu"].get("integrated", True):
            continue
        if ext_filters.get("require_oled") and "OLED" not in str(lap["specs"]["display"].get("panel_type") or "").upper():
            continue
        if ext_filters.get("require_touchscreen") and not lap["specs"]["display"].get("touchscreen"):
            continue
        base_pool.append(lap)

    gates = p_cfg["implicit_gates"]
    persona_pool: List[Dict[str, Any]] = []
    for lap in base_pool:
        s = lap["specs"]
        dm = lap["derived_metrics"]
        if gates.get("require_dgpu") and s["gpu"].get("integrated", True):
            continue
        if gates.get("require_nvidia") and not _is_nvidia_gpu(lap):
            continue
        if gates.get("min_vram_gb") and (s["gpu"].get("vram_gb") or 0) < gates["min_vram_gb"]:
            continue
        if gates.get("min_refresh_hz") and (s["display"].get("refresh_rate_hz") or 60) < gates["min_refresh_hz"]:
            continue
        if gates.get("min_ram_gb") and (s["memory"].get("capacity_gb") or 0) < gates["min_ram_gb"]:
            continue
        if gates.get("min_cpu_cores") and (s["cpu"].get("cores") or 0) < gates["min_cpu_cores"]:
            continue
        if gates.get("require_creator_display"):
            gtier = dm["display"].get("color_gamut_tier", "").lower()
            if "100% srgb" not in gtier and "dci-p3" not in gtier:
                continue
        if gates.get("max_weight_kg") and dm["mobility"].get("weight_kg", 2.0) > gates["max_weight_kg"]:
            continue
        persona_pool.append(lap)

    gates_relaxed = False
    if len(persona_pool) < 3 and len(base_pool) >= 3:
        persona_pool = base_pool
        gates_relaxed = True

    applied_floor_egp = min_budget_egp if min_budget_egp is not None else 0.0
    scoped_pool = persona_pool
    if min_budget_egp is None and apply_smart_60pct_floor and len(persona_pool) > min_floor_candidates:
        floor_60 = round(max_budget_egp * 0.60, 0)
        pool_60 = [
            l for l in persona_pool
            if l["derived_metrics"]["topsis_inputs"]["effective_price_egp"] >= floor_60
        ]
        if len(pool_60) >= min_floor_candidates:
            scoped_pool = pool_60
            applied_floor_egp = floor_60
        else:
            floor_45 = round(max_budget_egp * 0.45, 0)
            pool_45 = [
                l for l in persona_pool
                if l["derived_metrics"]["topsis_inputs"]["effective_price_egp"] >= floor_45
            ]
            if len(pool_45) >= min_floor_candidates:
                scoped_pool = pool_45
                applied_floor_egp = floor_45

    if not scoped_pool:
        return {
            "persona": p_key,
            "persona_label_ar": p_cfg["label_ar"],
            "persona_label_en": p_cfg["label_en"],
            "gates_relaxed_for_low_budget": gates_relaxed,
            "total_candidates_before_floor": len(base_pool),
            "total_candidates_after_gates_and_floor": 0,
            "applied_budget_window_egp": [applied_floor_egp, max_budget_egp],
            "parsed_text_prompt": parsed_prompt,
            "effective_weights": final_weights_dict,
            "results": [],
        }

    mat = np.array(
        [
            [
                _extract_matrix_cell(
                    l["derived_metrics"]["topsis_inputs"],
                    k,
                    l.get("canonical_id", ""),
                    adjusted_nlp_scores,
                )
                for k in TOPSIS_CRITERIA_KEYS
            ]
            for l in scoped_pool
        ],
        dtype=float,
    )
    scores = _run_topsis_vector(mat, weights_vec, IS_BENEFIT_CRITERION)

    ranked_indices = np.argsort(-scores)[:top_k]
    results = []
    for rank_idx, idx in enumerate(ranked_indices, start=1):
        row_i = int(idx)
        lap = scoped_pool[row_i]
        score_val = float(scores[row_i])
        ti = lap["derived_metrics"]["topsis_inputs"]
        eff_price = ti.get("effective_price_egp")
        p_val_score = _compute_persona_value_score(lap, mat[row_i, :13], hw_weights_13, p_key, eff_price)
        why = _build_why_recommended(lap, p_key)
        results.append({
            "rank": rank_idx,
            "canonical_id": lap["canonical_id"],
            "brand": lap.get("brand"),
            "laptop_family": lap.get("laptop_family"),
            "laptop_model": lap.get("laptop_model"),
            "title": lap.get("title"),
            "thumbnail_url": lap.get("thumbnail_url"),
            "topsis_match_score": score_val,
            "persona_value_score": p_val_score,
            "value_score": ti.get("value_score"),
            "effective_price_egp": eff_price,
            "cheapest_store": lap.get("cheapest_store"),
            "available_stores": lap.get("available_stores"),
            "prices_by_store": lap.get("prices_by_store"),
            "why_recommended_ar": why["ar"],
            "why_recommended_en": why["en"],
            "topsis_inputs": ti,
        })

    return {
        "persona": p_key,
        "persona_label_ar": p_cfg["label_ar"],
        "persona_label_en": p_cfg["label_en"],
        "gates_relaxed_for_low_budget": gates_relaxed,
        "total_candidates_before_floor": len(base_pool),
        "total_candidates_after_gates_and_floor": len(scoped_pool),
        "applied_budget_window_egp": [applied_floor_egp, max_budget_egp],
        "parsed_text_prompt": parsed_prompt,
        "effective_weights": final_weights_dict,
        "results": results,
    }


def apply_persona_scores_to_catalog(catalog: Dict[str, Any]) -> Dict[str, Any]:
    """Compute and attach static `persona_scores` (`hardware_fit`, `value_fit`) across all 16 personas."""
    laptops = catalog.get("laptops", [])
    if not laptops:
        return catalog

    hw_keys = TOPSIS_CRITERIA_KEYS[:13]
    hw_mat = np.array(
        [
            [
                _extract_matrix_cell(
                    l["derived_metrics"]["topsis_inputs"],
                    k,
                    l.get("canonical_id", ""),
                    None,
                )
                for k in hw_keys
            ]
            for l in laptops
        ],
        dtype=float,
    )
    val_col = np.array(
        [[float(l["derived_metrics"]["topsis_inputs"].get("value_score") or 50.0)] for l in laptops],
        dtype=float,
    )
    hw_plus_val_mat = np.hstack([hw_mat, val_col])

    for lap in laptops:
        lap["derived_metrics"]["persona_scores"] = {}

    for p_key, p_cfg in PERSONA_CONFIGS.items():
        w_hw_list = [p_cfg["weights"].get(k, DEFAULT_COMMUNITY_NLP_WEIGHT) for k in hw_keys]
        w_hw = np.array(w_hw_list, dtype=float)
        w_val = np.array(w_hw_list + [p_cfg["weights"]["effective_price_egp"] * 1.5], dtype=float)

        hw_scores = _run_topsis_vector(hw_mat, w_hw, [True] * 13)
        val_scores = _run_topsis_vector(hw_plus_val_mat, w_val, [True] * 14)

        for i, lap in enumerate(laptops):
            lap["derived_metrics"]["persona_scores"][p_key] = {
                "hardware_fit": float(hw_scores[i]),
                "value_fit": float(val_scores[i]),
            }

    return catalog
