"""Domain constants, regexes and bilingual anchor texts for review enrichment.

Pure Python standard library only: no I/O, environment access, HTTP or ML imports.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

ENRICHER_SCHEMA_VERSION = "v2_yt_pipeline"
DEFAULT_PRIMARY_MODEL = "claude-haiku-5.5"
DEFAULT_FALLBACK_MODEL = "gpt-oss-120b"
DEFAULT_DELTA_CACHE_PATH = "enricher_delta_cache.json"

ASPECT_KEYS: Tuple[str, ...] = (
    "thermals_score",
    "acoustics_score",
    "build_and_hinges_score",
    "keyboard_and_trackpad_score",
    "real_battery_and_reliability_score",
)

# Verified against SovereignEG GET /v1/models EGP pricing
SOVEREIGNEG_PRICING_EGP_PER_1M: Dict[str, Dict[str, float]] = {
    "qwen3.7-flash": {"input": 1.7656, "output": 7.6508},
    "gpt-oss-120b": {"input": 2.1775, "output": 10.0049},
    "claude-haiku-5.5": {"input": 5.8852, "output": 29.4261},
}

ENRICHMENT_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["aspect_scores", "pros_en", "pros_ar", "cons_en", "cons_ar"],
    "properties": {
        "aspect_scores": {
            "type": "object",
            "additionalProperties": False,
            "required": list(ASPECT_KEYS),
            "properties": {k: {"type": "number"} for k in ASPECT_KEYS},
        },
        "pros_en": {
            "type": "array",
            "items": {"type": "string"},
        },
        "pros_ar": {
            "type": "array",
            "items": {"type": "string"},
        },
        "cons_en": {
            "type": "array",
            "items": {"type": "string"},
        },
        "cons_ar": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}

_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")
_CODE_BLOCK_RE = re.compile(r"```.*?```", flags=re.DOTALL)
_DETAILS_BLOCK_RE = re.compile(r"<details>.*?</details>", flags=re.DOTALL | re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)

_NOISE_PATTERNS = re.compile(
    r"(?i)(subscribe to (my|the) channel|hit the bell|like and subscribe|"
    r"check out (the )?links? (in the )?description|use my (affiliate )?code|"
    r"sponsored by|this video is sponsored|patreon\.com|gaminglaptop\.deals|"
    r"should i buy this|which laptop should i get|can anyone help|"
    r"pls help|please help|bazzite|lspci|lsmod|modinfo|kernel modules|"
    r"بكام|سعره كام|ممكن ترشيح|تنصحوني بإيه|حد جرب الجهاز|ازاي اثبت ويندوز)"
)

_DESKTOP_PART_RE = re.compile(
    r"(?i)(?:\b(?:B850M?|B860M?|B760M?|B650M?|X870E?|Z790|Z890|H610|A620|AM5|LGA\s?1[78]51|"
    r"mini-?ATX|micro-?ATX|motherboard|DisplayPort\s*2\.1b?|3\.\d+-?slot|GDDR7.*192bit)\b|"
    r"(?:ال)?لوحة\s+(?:ال)?أم|كارت\s+الشاشة|تجميعة|فتحة\s+PCIe)"
)
_LAPTOP_CONTEXT_RE = re.compile(
    r"(?i)(?:\b(?:laptop|notebook|battery|whr|hinge|hinges|trackpad|touchpad|"
    r"webcam|charger|adapter|lid|keyboard flex|portability)\b|لابتوب|بطارية|مفصلات|تاتش باد)"
)

# 10 Semantic Anchors (Pro + Con per aspect) + 1 Noise anchor for Jina-v3 filtering
_PRO_ANCHORS: Dict[str, str] = {
    "thermals_score": (
        "Effective cooling performance, low CPU and GPU temperatures under gaming or stress loads, "
        "vapor chamber or heatpipes, cool keyboard surface, no thermal throttling. "
        "نظام تبريد ممتاز وحرارة منخفضة تحت الضغط بدون اختناق حراري"
    ),
    "acoustics_score": (
        "Quiet fan operation during everyday work and reasonable low fan noise under gaming load, "
        "no high-pitched coil whine. مراوح هادئة وصوت منخفض بدون ضوضاء مزعجة"
    ),
    "build_and_hinges_score": (
        "Solid aluminum or rigid chassis construction, zero deck flex, smooth sturdy hinges, "
        "premium durable build quality and good upgradeability. "
        "شاسيه متين وألومنيوم قوي ومفصلات ثابتة وجودة تصنيع عالية"
    ),
    "keyboard_and_trackpad_score": (
        "Comfortable tactile keyboard with good key travel, clean backlight, and large smooth "
        "responsive glass touchpad. كيبورد مريح للكتابة وتاتش باد سلس ودقيق"
    ),
    "real_battery_and_reliability_score": (
        "Long real-world battery life lasting many hours unplugged, bright 100% sRGB or OLED display, "
        "good color accuracy, dependable everyday reliability. "
        "بطارية تدوم طويلاً وشاشة مشرقة بألوان دقيقة واعتمادية ممتازة"
    ),
}

_CON_ANCHORS: Dict[str, str] = {
    "thermals_score": (
        "High CPU or GPU overheating up to 95-100 degrees Celsius, thermal throttling, "
        "hot keyboard or palm rest during load. سخونة عالية وارتفاع حرارة المعالج واختناق حراري"
    ),
    "acoustics_score": (
        "Very loud roaring turbo fan noise under load, jet-engine fans requiring headphones, "
        "annoying coil whine. صوت مراوح عالي جداً ومزعج مع الألعاب والضغط"
    ),
    "build_and_hinges_score": (
        "Cheap plastic build, noticeable keyboard deck or lid flex, wobbly weak hinges, "
        "fingerprint magnet or creaking frame. خامات بلاستيكية ضعيفة ومفصلات مهتزة"
    ),
    "keyboard_and_trackpad_score": (
        "Shallow mushy keyboard keys, cramped arrow or numpad layout, rattling or stiff small "
        "plastic trackpad. كيبورد ضعيف أو تاتش باد صغير غير مريح"
    ),
    "real_battery_and_reliability_score": (
        "Short poor battery life under 3-4 hours, dim washed-out 45% NTSC 250-nit screen, "
        "backlight bleed, driver crashes or hardware defects. "
        "بطارية ضعيفة تفرغ بسرعة أو شاشة باهتة وسطوع منخفض أو مشاكل اعتمادية"
    ),
}

_NOISE_ANCHOR = (
    "YouTube channel subscription reminder, affiliate link promotion, sponsor ad read, "
    "unrelated desktop motherboard specs, Linux kernel driver log, or user buying question. "
    "إعلان قناة أو سؤال شراء من مستخدم أو مواصفات قطع كمبيوتر مكتبي"
)

_ASPECT_KEYWORDS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "thermals_score": {
        "pro": ("cool", "cooling", "thermal", "temp", "degrees", "heatsink", "heatpipe", "vapor chamber", "no throttling", "تبريد", "حرارة ممتازة"),
        "con": ("overheat", "throttl", "throttle", "95c", "95°c", "99c", "100c", "runs hot", "very hot", "سخونة", "حرارة عالية", "اختناق"),
    },
    "acoustics_score": {
        "pro": ("quiet", "silent", "inaudible", "low fan noise", "هادئ", "صوت هادئ"),
        "con": ("loud", "noisy", "jet engine", "annoying fan", "coil whine", "whine", "decibel", "db", "مزعج", "صوت المراوح عالي"),
    },
    "build_and_hinges_score": {
        "pro": ("aluminum", "metal", "magnesium", "sturdy", "solid", "rigid", "mil-std", "hinge", "upgrad", "ram slot", "m.2", "معدن", "متين", "مفصلات قوية"),
        "con": ("plastic", "flex", "wobble", "cheap", "flimsy", "creak", "fingerprint", "soldered ram", "بلاستيك", "اهتزاز", "مفصلات ضعيفة"),
    },
    "keyboard_and_trackpad_score": {
        "pro": ("tactile", "key travel", "comfortable keyboard", "backlit", "rgb", "glass touchpad", "smooth trackpad", "كيبورد مريح", "تاتش باد"),
        "con": ("mushy", "shallow", "cramped", "rattle", "rattly", "small touchpad", "stiff trackpad", "كيبورد ضعيف", "تاتش باد صغير"),
    },
    "real_battery_and_reliability_score": {
        "pro": ("battery life", "hours", "90wh", "90-w", "80wh", "70wh", "oled", "100% srgb", "bright", "nits", "accurate colors", "mux", "بطارية ممتازة", "شاشة ممتازة"),
        "con": ("poor battery", "short battery", "45% ntsc", "dim", "250 nits", "washed out", "bleed", "backlight bleed", "latency", "glitch", "بطارية ضعيفة", "شاشة باهتة"),
    },
}

_ASPECT_FALLBACK_AR: Dict[str, Tuple[str, str]] = {
    "thermals_score": (
        "أداء تبريد مستقر نسبياً يحافظ على ترددات المعالج وكارت الشاشة في المهام اليومية والألعاب المتوسطة",
        "قد ترتفع درجات حرارة المعالج تحت الضغط المتواصل مما يتطلب تهوية جيدة أو قاعدة تبريد في الصيف",
    ),
    "acoustics_score": (
        "صوت المراوح مقبول وهادئ في أوضاع الاستخدام العادي والتصفح",
        "صوت المراوح يرتفع بوضوح عند تشغيل وضع الأداء الأقصى أو الألعاب الثقيلة",
    ),
    "build_and_hinges_score": (
        "جودة تصنيع جيدة وتصميم عملي يتحمل التنقل والعمل اليومي مع مفصلات ثابتة",
        "وجود بعض المرونة أو الاعتماد على خامات بلاستيكية في أجزاء من الهيكل الخارجي مقارنة بالفئات المعدنية",
    ),
    "keyboard_and_trackpad_score": (
        "كيبورد مريح للاستخدام والكتابة الطويلة مع لوحة لمس دقيقة وسلسة الاستجابة",
        "تخطيط بعض الأزرار أو حجم لوحة اللمس قد لا يناسب جميع المستخدمين مقارنة بالأجهزة الأعلى فئة",
    ),
    "real_battery_and_reliability_score": (
        "توازن جيد بين الشاشة والبطارية يناسب مهام الدراسة والعمل المتنقل بثبات",
        "عمر البطارية أو سطوع الشاشة وتغطية الألوان يظل متوسطاً ولا يناسب العمل الطويل بدون شاحن في المهام الشاقة",
    ),
}

_ASPECT_FALLBACK_EN: Dict[str, Tuple[str, str]] = {
    "thermals_score": (
        "Thermals remain controlled under sustained workloads without severe CPU/GPU throttling",
        "CPU/GPU temperatures climb noticeably under heavy stress tests in warm ambient conditions",
    ),
    "acoustics_score": (
        "Fans stay unobtrusive during light productivity and quiet-mode operation",
        "Fan noise ramps up noticeably during Turbo or sustained gaming loads",
    ),
    "build_and_hinges_score": (
        "Sturdy everyday chassis construction with dependable hinges and solid upgradeability",
        "Plastic chassis panels exhibit minor flex compared to all-aluminum premium ultrabooks",
    ),
    "keyboard_and_trackpad_score": (
        "Comfortable keyboard travel and responsive touchpad suited for daily typing",
        "Keyboard key travel or touchpad feel is average for the price tier",
    ),
    "real_battery_and_reliability_score": (
        "Display clarity and battery efficiency deliver solid day-to-day reliability",
        "Unplugged battery endurance and outdoor display brightness/color gamut remain modest",
    ),
}

_HW_UNIT_RE = re.compile(
    r"(?i)\b(\d+\s*(?:w|wh|whr|hz|nits|db|°c|fps|gb|tb|mm|hrs?|hours?|ms|%)|"
    r"cpu|gpu|rtx|gtx|ryzen|core\s+ultra|oled|ips|srgb|ntsc|battery|charging|"
    r"thermal|cool|heat|throttl|fan|loud|quiet|noise|hinge|build|plastic|"
    r"aluminum|metal|flex|keyboard|trackpad|touchpad|display|screen|bright|"
    r"speaker|port|upgrad\w*|ram|ssd|wifi)\b|"
    r"حرارة|تبريد|مراوح|صوت|بطارية|شاشة|مفصلات|خامات|كيبورد|تاتش"
)
