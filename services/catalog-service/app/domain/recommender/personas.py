"""Persona definitions, criteria configuration, and bilingual prompt parsing.

This module defines the 7 user personas, their multi-criteria weight distributions,
implicit hardware gates, and a lightweight bilingual (Arabic/English) text prompt parser.
"""

from enum import StrEnum
import re
from typing import Any

# =============================================================================
# 1. TOPSIS CRITERIA & BENEFIT/COST KEYS
# =============================================================================
# 9 Benefit criteria (higher is better) + 1 Cost criterion (effective_price_egp, lower is better)
TOPSIS_CRITERIA_KEYS: list[str] = [
    "cpu_score",
    "gpu_score",
    "power_therm_score",
    "display_score",
    "mobility_score",
    "longevity_score",
    "ergonomics_score",
    "connectivity_score",
    "community_nlp_score",
    "effective_price_egp",
]

IS_BENEFIT_CRITERION: list[bool] = [
    True,  # cpu_score
    True,  # gpu_score
    True,  # power_therm_score
    True,  # display_score
    True,  # mobility_score
    True,  # longevity_score
    True,  # ergonomics_score
    True,  # connectivity_score
    True,  # community_nlp_score (Benefit: higher real-world review score is better)
    False,  # effective_price_egp (Cost criterion: cheaper within the budget window is better)
]


class PersonaType(StrEnum):
    """The 7 official personas supported by the recommender engine."""

    GAMING = "gaming"
    AI_AND_GAME_DEV = "ai_and_game_dev"
    PROGRAMMING = "programming"
    CONTENT_CREATION = "content_creation"
    STUDENT_AND_OFFICE = "student_and_office"
    BUSINESS_AND_MOBILITY = "business_and_mobility"
    BALANCED = "balanced"


PERSONA_CONFIGS: dict[str, dict[str, Any]] = {
    PersonaType.GAMING: {
        "label_ar": "الألعاب الثقيلة والـ Esports",
        "label_en": "Heavy Gaming & Esports",
        "weights": {
            "cpu_score": 0.15,
            "gpu_score": 0.30,
            "power_therm_score": 0.13,
            "display_score": 0.13,
            "mobility_score": 0.03,
            "longevity_score": 0.05,
            "ergonomics_score": 0.02,
            "connectivity_score": 0.03,
            "community_nlp_score": 0.06,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "min_refresh_hz": 120,
            "min_ram_gb": 8,
        },
    },
    PersonaType.AI_AND_GAME_DEV: {
        "label_ar": "الذكاء الاصطناعي وتطوير الألعاب والـ 3D",
        "label_en": "AI / ML, Game Dev & 3D Rendering",
        "weights": {
            "cpu_score": 0.19,
            "gpu_score": 0.26,
            "power_therm_score": 0.11,
            "display_score": 0.10,
            "mobility_score": 0.03,
            "longevity_score": 0.09,
            "ergonomics_score": 0.03,
            "connectivity_score": 0.03,
            "community_nlp_score": 0.06,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "require_dgpu": True,
            "min_ram_gb": 16,
        },
    },
    PersonaType.PROGRAMMING: {
        "label_ar": "البرمجة وهندسة البرمجيات",
        "label_en": "Programming & Software Engineering",
        "weights": {
            "cpu_score": 0.24,
            "gpu_score": 0.06,
            "power_therm_score": 0.08,
            "display_score": 0.10,
            "mobility_score": 0.11,
            "longevity_score": 0.13,
            "ergonomics_score": 0.07,
            "connectivity_score": 0.05,
            "community_nlp_score": 0.06,
            "effective_price_egp": 0.10,
        },
        "implicit_gates": {
            "min_ram_gb": 16,
            "min_cpu_cores": 6,
        },
    },
    PersonaType.CONTENT_CREATION: {
        "label_ar": "المونتاج والتصميم الجرافيكي وصناعة المحتوى",
        "label_en": "Video Editing, Design & Content Creation",
        "weights": {
            "cpu_score": 0.19,
            "gpu_score": 0.21,
            "power_therm_score": 0.09,
            "display_score": 0.23,
            "mobility_score": 0.05,
            "longevity_score": 0.05,
            "ergonomics_score": 0.03,
            "connectivity_score": 0.03,
            "community_nlp_score": 0.06,
            "effective_price_egp": 0.06,
        },
        "implicit_gates": {
            "min_ram_gb": 16,
            "require_creator_display": True,  # 100% sRGB, DCI-P3, or OLED
        },
    },
    PersonaType.STUDENT_AND_OFFICE: {
        "label_ar": "الدراسة والجامعة والعمل المكتبي",
        "label_en": "Student, University & Office Work",
        "weights": {
            "cpu_score": 0.15,
            "gpu_score": 0.03,
            "power_therm_score": 0.05,
            "display_score": 0.10,
            "mobility_score": 0.22,
            "longevity_score": 0.07,
            "ergonomics_score": 0.11,
            "connectivity_score": 0.04,
            "community_nlp_score": 0.06,
            "effective_price_egp": 0.17,
        },
        "implicit_gates": {
            "min_ram_gb": 8,
            "max_weight_kg": 2.35,
        },
    },
    PersonaType.BUSINESS_AND_MOBILITY: {
        "label_ar": "البيزنس والتنقل المستمر والاجتماعات",
        "label_en": "Executive Business & Ultraportable Mobility",
        "weights": {
            "cpu_score": 0.15,
            "gpu_score": 0.03,
            "power_therm_score": 0.05,
            "display_score": 0.11,
            "mobility_score": 0.28,
            "longevity_score": 0.05,
            "ergonomics_score": 0.13,
            "connectivity_score": 0.06,
            "community_nlp_score": 0.06,
            "effective_price_egp": 0.08,
        },
        "implicit_gates": {
            "min_ram_gb": 8,
            "max_weight_kg": 1.90,
        },
    },
    PersonaType.BALANCED: {
        "label_ar": "استخدام شامل متوازن (أفضل قيمة)",
        "label_en": "Balanced All-Rounder",
        "weights": {
            "cpu_score": 0.19,
            "gpu_score": 0.17,
            "power_therm_score": 0.08,
            "display_score": 0.13,
            "mobility_score": 0.09,
            "longevity_score": 0.07,
            "ergonomics_score": 0.05,
            "connectivity_score": 0.04,
            "community_nlp_score": 0.06,
            "effective_price_egp": 0.12,
        },
        "implicit_gates": {
            "min_ram_gb": 8,
        },
    },
}


# =============================================================================
# 2. BILINGUAL (AR/EN) TEXT PROMPT PARSER
# =============================================================================
def parse_user_text_prompt(prompt: str | None) -> dict[str, Any]:
    """Lightweight, zero-latency bilingual parser for user text prompts.

    Extracts:
      1. `extracted_filters`: hard constraints if explicitly mentioned
         (e.g., '32GB RAM', '1TB', 'OLED', 'touchscreen').
      2. `weight_boosts`: additive boosts to TOPSIS criteria weights based
         on user intent keywords in Arabic and English.
    """
    if not prompt or not str(prompt).strip():
        return {"extracted_filters": {}, "weight_boosts": {}}

    txt = str(prompt).lower()
    extracted_filters: dict[str, Any] = {}
    weight_boosts: dict[str, float] = {}

    # --- A0. Baseline Dual-Impact Review Weight Boost ---
    # Any free-text prompt signals that real-world experiential evidence matters.
    weight_boosts["community_nlp_score"] = weight_boosts.get("community_nlp_score", 0.0) + 0.08
    if any(
        k in txt
        for k in [
            "خامات",
            "مفصلات",
            "عيوب",
            "مشاكل",
            "مضمون",
            "اعتمادية",
            "صوت المراوح",
            "سخونة",
            "بيسخن",
            "مبيسخنش",
            "build",
            "hinge",
            "reliable",
            "reliability",
            "issues",
            "quiet",
            "fan noise",
            "thermals",
        ]
    ):
        weight_boosts["community_nlp_score"] = weight_boosts.get("community_nlp_score", 0.0) + 0.06

    # --- A. Extract Explicit Hardware Constraints from Text ---
    if re.search(r"\b(64\s*gb|64\s*جيجا)\b", txt):
        extracted_filters["min_ram_gb"] = 64
    elif re.search(r"\b(32\s*gb|32\s*جيجا)\b", txt):
        extracted_filters["min_ram_gb"] = 32
    elif re.search(r"\b(24\s*gb|24\s*جيجا)\b", txt):
        extracted_filters["min_ram_gb"] = 24
    elif re.search(r"\b(16\s*gb|16\s*جيجا)\b", txt):
        extracted_filters["min_ram_gb"] = 16

    if re.search(r"\b(2\s*tb|2000\s*gb|2\s*تيرا)\b", txt):
        extracted_filters["min_storage_gb"] = 2048
    elif re.search(r"\b(1\s*tb|1000\s*gb|1024\s*gb|تيرا|1\s*تيرا)\b", txt):
        extracted_filters["min_storage_gb"] = 1024

    if any(k in txt for k in ["oled", "اوليد", "أوليد"]):
        extracted_filters["require_oled"] = True
    if any(k in txt for k in ["touch", "تاتش", "لمس", "x360", "flip", "2-in-1"]):
        extracted_filters["require_touchscreen"] = True

    # Explicit AAA / Ultra / dedicated-GPU intent forces a real discrete GPU.
    if any(
        k in txt
        for k in [
            "cyberpunk",
            "سايبر بانك",
            "سايبربانك",
            "الترا",
            "ألترا",
            "ultra",
            "aaa",
            "rtx",
            "كارت خارجي",
            "dedicated gpu",
            "warzone",
            "red dead",
            "بلندر",
            "blender",
            "unreal",
        ]
    ):
        extracted_filters["require_dgpu"] = True

    # --- B. Extract Dynamic Weight Boosts from Intent Keywords ---
    # 1. Mobility / Battery / Lightweight
    if any(
        k in txt
        for k in [
            "بطاريه",
            "بطارية",
            "خفيف",
            "تنقل",
            "سفر",
            "مواصلات",
            "محاضرات",
            "battery",
            "lightweight",
            "portable",
            "travel",
            "thin",
        ]
    ):
        weight_boosts["mobility_score"] = weight_boosts.get("mobility_score", 0.0) + 0.15

    # 2. Display / Colors / Screen / OLED
    if any(
        k in txt
        for k in [
            "شاشه",
            "شاشة",
            "الوان",
            "ألوان",
            "دقة",
            "سطوع",
            "مونتاج",
            "جرافيك",
            "display",
            "screen",
            "color",
            "srgb",
            "oled",
            "hdr",
        ]
    ):
        weight_boosts["display_score"] = weight_boosts.get("display_score", 0.0) + 0.14

    # 3. GPU / Gaming / Graphics / Rendering
    if any(
        k in txt
        for k in [
            "كارت شاشه",
            "كارت شاشة",
            "العاب",
            "ألعاب",
            "فريمات",
            "رندر",
            "جيمز",
            "جيمنج",
            "يشغل",
            "الترا",
            "ألترا",
            "سايبر بانك",
            "سايبربانك",
            "فيفا",
            "فورزا",
            "فالورانت",
            "بيس",
            "ببجي",
            "جاتا",
            "بلندر",
            "gaming",
            "fps",
            "rtx",
            "gpu",
            "render",
            "3d",
            "ultra",
            "cyberpunk",
            "gta",
            "fifa",
            "fc24",
            "fc25",
            "valorant",
            "cs2",
            "warzone",
            "aaa",
            "unreal",
            "unity",
            "blender",
        ]
    ):
        weight_boosts["gpu_score"] = weight_boosts.get("gpu_score", 0.0) + 0.15
        weight_boosts["power_therm_score"] = weight_boosts.get("power_therm_score", 0.0) + 0.06

    # 4. CPU / Multitasking / Heavy Coding / VMs
    if any(
        k in txt
        for k in [
            "معالج",
            "بروسيسور",
            "برمجه",
            "برمجة",
            "محاكاة",
            "داتا",
            "كود",
            "cpu",
            "processor",
            "coding",
            "docker",
            "vm",
            "multitask",
        ]
    ):
        weight_boosts["cpu_score"] = weight_boosts.get("cpu_score", 0.0) + 0.14

    # 5. Cooling / Thermals / Power
    if any(
        k in txt
        for k in [
            "تبريد",
            "حراره",
            "حرارة",
            "مراوح",
            "سخونة",
            "باور",
            "cooling",
            "thermal",
            "heat",
            "tgp",
            "watt",
        ]
    ):
        weight_boosts["power_therm_score"] = weight_boosts.get("power_therm_score", 0.0) + 0.14

    # 6. Upgradeability / Longevity / Future-proof
    if any(
        k in txt
        for k in [
            "تطوير",
            "ترقيه",
            "ترقية",
            "يعيش",
            "مستقبل",
            "رامات بتزيد",
            "upgrade",
            "future",
            "slots",
            "longevity",
            "expand",
        ]
    ):
        weight_boosts["longevity_score"] = weight_boosts.get("longevity_score", 0.0) + 0.14

    # 7. Keyboard / Webcam / Audio / Meetings
    if any(
        k in txt
        for k in [
            "كيبورد",
            "كاميرا",
            "صوت",
            "اجتماعات",
            "زووم",
            "بصمه",
            "بصمة",
            "keyboard",
            "webcam",
            "camera",
            "mic",
            "audio",
            "zoom",
        ]
    ):
        weight_boosts["ergonomics_score"] = weight_boosts.get("ergonomics_score", 0.0) + 0.12

    # 8. Ports / Thunderbolt / Type-C / LAN
    if any(
        k in txt
        for k in [
            "منافذ",
            "تايب سي",
            "ثندربولت",
            "لان",
            "شاشات خارجية",
            "ports",
            "thunderbolt",
            "usb-c",
            "hdmi",
            "ethernet",
            "lan",
        ]
    ):
        weight_boosts["connectivity_score"] = weight_boosts.get("connectivity_score", 0.0) + 0.12

    # 9. Budget / Cheapest / Value
    if any(
        k in txt
        for k in [
            "ارخص",
            "أرخص",
            "توفير",
            "سعر",
            "اقتصادي",
            "على قد الايد",
            "cheap",
            "budget",
            "value",
            "save",
            "affordable",
        ]
    ):
        weight_boosts["effective_price_egp"] = weight_boosts.get("effective_price_egp", 0.0) + 0.14

    return {
        "extracted_filters": extracted_filters,
        "weight_boosts": weight_boosts,
    }


def get_persona_db_query_spec(persona: str, max_budget_egp: float) -> dict[str, Any]:
    """Return baseline query filter specifications for database queries.

    Relaxes gates automatically if the user's budget is under common thresholds.
    """
    p_key = persona if persona in PERSONA_CONFIGS else PersonaType.BALANCED
    gates = dict(PERSONA_CONFIGS[p_key]["implicit_gates"])

    # If budget is under 35,000 EGP, relax 16GB RAM gate to 8GB and dGPU gate automatically
    if max_budget_egp < 35000:
        if gates.get("min_ram_gb", 8) > 8:
            gates["min_ram_gb"] = 8
        if max_budget_egp < 30000 and gates.get("require_dgpu"):
            gates["require_dgpu"] = False
            gates.pop("min_refresh_hz", None)

    return {
        "in_stock_active": True,
        "max_price_egp": max_budget_egp,
        "persona_gates": gates,
    }
