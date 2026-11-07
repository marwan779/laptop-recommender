"""Shared Arabic/English vocabulary for review identity, queries, and matching.

Everything here is pure data and text normalization. No I/O dependencies are
allowed in the domain layer.
"""

from __future__ import annotations

import re

ARABIC_DIACRITICS_RE = re.compile(r"[\u064B-\u0652\u0670\u0640]")
_ARABIC_NUMERALS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_lookup(value: str | None) -> str:
    """Normalize text for vocabulary lookups and Arabic/English matching.

    This intentionally does not strip Latin hyphens from model codes. It is
    only used for human-language aliases and keyword matching.
    """

    if not value:
        return ""
    text = value.translate(_ARABIC_NUMERALS)
    text = ARABIC_DIACRITICS_RE.sub("", text)
    text = (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    text = re.sub(r"[\s\-_]+", " ", text)
    return text.strip().lower()


_BRAND_ALIAS_PAIRS: tuple[tuple[str, str], ...] = (
    ("ASUS", "ASUS"),
    ("أسوس", "ASUS"),
    ("اسوس", "ASUS"),
    ("Lenovo", "Lenovo"),
    ("لينوفو", "Lenovo"),
    ("HP", "HP"),
    ("Hewlett Packard", "HP"),
    ("إتش بي", "HP"),
    ("اتش بي", "HP"),
    ("هيويت باكارد", "HP"),
    ("Dell", "Dell"),
    ("ديل", "Dell"),
    ("Acer", "Acer"),
    ("إيسر", "Acer"),
    ("ايسر", "Acer"),
    ("Apple", "Apple"),
    ("أبل", "Apple"),
    ("ابل", "Apple"),
    ("MSI", "MSI"),
    ("إم إس آي", "MSI"),
    ("ام اس اي", "MSI"),
    ("Gigabyte", "Gigabyte"),
    ("جيجابايت", "Gigabyte"),
    ("Huawei", "Huawei"),
    ("هواوي", "Huawei"),
    ("Xiaomi", "Xiaomi"),
    ("شاومي", "Xiaomi"),
    ("Redmi", "Redmi"),
    ("ريدمي", "Redmi"),
    ("Realme", "Realme"),
    ("ريلمي", "Realme"),
    ("Samsung", "Samsung"),
    ("سامسونج", "Samsung"),
    ("Microsoft", "Microsoft"),
    ("مايكروسوفت", "Microsoft"),
    ("Razer", "Razer"),
    ("ريزر", "Razer"),
    ("Alienware", "Alienware"),
    ("ألينوير", "Alienware"),
    ("الينوير", "Alienware"),
    ("Infinix", "Infinix"),
    ("إنفينيكس", "Infinix"),
    ("انفينيكس", "Infinix"),
    ("Tecno", "Tecno"),
    ("تكنو", "Tecno"),
    ("Toshiba", "Toshiba"),
    ("توشيبا", "Toshiba"),
    ("Sony", "Sony"),
    ("سوني", "Sony"),
    ("Fujitsu", "Fujitsu"),
    ("فوجيتسو", "Fujitsu"),
    ("Panasonic", "Panasonic"),
    ("باناسونيك", "Panasonic"),
    ("LG", "LG"),
    ("إل جي", "LG"),
    ("ال جي", "LG"),
    ("Honor", "Honor"),
    ("هونر", "Honor"),
)

BRAND_ALIASES: dict[str, str] = {
    normalize_lookup(alias): canonical for alias, canonical in _BRAND_ALIAS_PAIRS
}

ARABIC_BRAND_NAMES: dict[str, str] = {
    "ASUS": "أسوس",
    "Lenovo": "لينوفو",
    "HP": "إتش بي",
    "Dell": "ديل",
    "Acer": "إيسر",
    "Apple": "أبل",
    "MSI": "إم إس آي",
    "Gigabyte": "جيجابايت",
    "Huawei": "هواوي",
    "Xiaomi": "شاومي",
    "Redmi": "ريدمي",
    "Realme": "ريلمي",
    "Samsung": "سامسونج",
    "Microsoft": "مايكروسوفت",
    "Razer": "ريزر",
    "Alienware": "ألينوير",
    "Infinix": "إنفينيكس",
    "Tecno": "تكنو",
    "Toshiba": "توشيبا",
    "Sony": "سوني",
    "Fujitsu": "فوجيتسو",
    "Panasonic": "باناسونيك",
    "LG": "إل جي",
    "Honor": "هونر",
}


_FAMILY_ALIAS_PAIRS: tuple[tuple[str, str], ...] = (
    ("Vivobook", "Vivobook"),
    ("فيفوبوك", "Vivobook"),
    ("فيڤوبوك", "Vivobook"),
    ("Zenbook", "Zenbook"),
    ("زين بوك", "Zenbook"),
    ("زينبوك", "Zenbook"),
    ("ROG", "ROG"),
    ("روج", "ROG"),
    ("TUF", "TUF"),
    ("تاف", "TUF"),
    ("Legion", "Legion"),
    ("ليجون", "Legion"),
    ("LOQ", "LOQ"),
    ("IdeaPad", "IdeaPad"),
    ("أيديا باد", "IdeaPad"),
    ("ايديا باد", "IdeaPad"),
    ("ThinkPad", "ThinkPad"),
    ("ثينك باد", "ThinkPad"),
    ("ثنك باد", "ThinkPad"),
    ("ThinkBook", "ThinkBook"),
    ("ثينك بوك", "ThinkBook"),
    ("Yoga", "Yoga"),
    ("يوجا", "Yoga"),
    ("Aspire", "Aspire"),
    ("أسباير", "Aspire"),
    ("اسباير", "Aspire"),
    ("Nitro", "Nitro"),
    ("نيترو", "Nitro"),
    ("Predator", "Predator"),
    ("بريداتور", "Predator"),
    ("Swift", "Swift"),
    ("سويفت", "Swift"),
    ("Victus", "Victus"),
    ("فيكتوس", "Victus"),
    ("Pavilion", "Pavilion"),
    ("بافيليون", "Pavilion"),
    ("Omen", "Omen"),
    ("أومين", "Omen"),
    ("اومين", "Omen"),
    ("Envy", "Envy"),
    ("إنفي", "Envy"),
    ("انفي", "Envy"),
    ("Spectre", "Spectre"),
    ("سبيكتر", "Spectre"),
    ("MacBook", "MacBook"),
    ("ماك بوك", "MacBook"),
    ("Galaxy Book", "Galaxy Book"),
    ("جالاكسي بوك", "Galaxy Book"),
    ("Katana", "Katana"),
    ("كاتانا", "Katana"),
    ("Raider", "Raider"),
    ("رايدر", "Raider"),
    ("Stealth", "Stealth"),
    ("ستيلث", "Stealth"),
    ("Modern", "Modern"),
    ("مودرن", "Modern"),
    ("Prestige", "Prestige"),
    ("بريستيج", "Prestige"),
    ("Gram", "Gram"),
    ("جرام", "Gram"),
    ("MateBook", "MateBook"),
    ("ميت بوك", "MateBook"),
    ("RedmiBook", "RedmiBook"),
    ("ريدمي بوك", "RedmiBook"),
    ("ProBook", "ProBook"),
    ("برو بوك", "ProBook"),
    ("EliteBook", "EliteBook"),
    ("إيليت بوك", "EliteBook"),
    ("ايليت بوك", "EliteBook"),
    ("Latitude", "Latitude"),
    ("لاتيتيود", "Latitude"),
    ("Inspiron", "Inspiron"),
    ("إنسبايرون", "Inspiron"),
    ("انسبايرون", "Inspiron"),
    ("Vostro", "Vostro"),
    ("فوسترو", "Vostro"),
    ("XPS", "XPS"),
    ("Alienware", "Alienware"),
    ("الينوير", "Alienware"),
    ("Surface", "Surface"),
    ("سيرفس", "Surface"),
)

FAMILY_ALIASES: dict[str, str] = {
    normalize_lookup(alias): canonical for alias, canonical in _FAMILY_ALIAS_PAIRS
}

ARABIC_FAMILY_NAMES: dict[str, str] = {
    "Vivobook": "فيفوبوك",
    "Zenbook": "زين بوك",
    "ROG": "روج",
    "TUF": "تاف",
    "Legion": "ليجون",
    "IdeaPad": "أيديا باد",
    "ThinkPad": "ثينك باد",
    "ThinkBook": "ثينك بوك",
    "Yoga": "يوجا",
    "Aspire": "أسباير",
    "Nitro": "نيترو",
    "Predator": "بريداتور",
    "Swift": "سويفت",
    "Victus": "فيكتوس",
    "Pavilion": "بافيليون",
    "Omen": "أومين",
    "Envy": "إنفي",
    "Spectre": "سبيكتر",
    "MacBook": "ماك بوك",
    "Galaxy Book": "جالاكسي بوك",
    "Katana": "كاتانا",
    "Raider": "رايدر",
    "Stealth": "ستيلث",
    "Modern": "مودرن",
    "Prestige": "بريستيج",
    "Gram": "جرام",
    "MateBook": "ميت بوك",
    "RedmiBook": "ريدمي بوك",
    "ProBook": "برو بوك",
    "EliteBook": "إيليت بوك",
    "Latitude": "لاتيتيود",
    "Inspiron": "إنسبايرون",
    "Vostro": "فوسترو",
    "Surface": "سيرفس",
}


REVIEW_INTENT_TERMS: tuple[str, ...] = tuple(
    normalize_lookup(term)
    for term in (
        "review",
        "reviewed",
        "hands-on",
        "hands on",
        "tested",
        "مراجعة",
        "تجربة",
        "تقييم",
    )
)


ACCESSORY_PHRASES: tuple[str, ...] = tuple(
    normalize_lookup(phrase)
    for phrase in (
        "laptop case",
        "laptop sleeve",
        "laptop bag",
        "carry bag",
        "backpack",
        "cover for",
        "skin for",
        "screen protector",
        "charger for",
        "power adapter",
        "docking station",
        "laptop stand",
        "cooling pad",
        "wireless mouse",
        "gaming mouse",
        "external keyboard",
        "external monitor",
        "usb hub",
        "laptop cable",
        "شنطة لابتوب",
        "حقيبة لابتوب",
        "كفر لابتوب",
        "حافظة لابتوب",
        "شاحن لابتوب",
        "محول طاقة",
        "ستاند لابتوب",
        "ماوس",
        "كيبورد خارجي",
        "شاشة خارجية",
        "كابل لابتوب",
    )
)


ASPECT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "battery": ("battery", "batteries", "charging", "بطارية", "شحن"),
    "performance": ("performance", "benchmark", "cpu", "أداء", "معالج"),
    "thermals": ("thermal", "thermals", "temperature", "heat", "حرارة", "حراره"),
    "noise": ("fan noise", "loud fan", "coil whine", "ضوضاء", "مروحة", "مروحه"),
    "display": ("display", "screen", "oled", "ips", "شاشة", "شاشه"),
    "keyboard": ("keyboard", "key travel", "لوحة مفاتيح", "كيبورد"),
    "build": ("build quality", "chassis", "hinge", "تصنيع", "جودة التصنيع", "مفصلة"),
    "speakers": ("speaker", "speakers", "audio", "سماعات", "صوت"),
    "webcam": ("webcam", "camera", "كاميرا", "ويب كام"),
    "price": ("price", "value", "worth it", "سعر", "قيمة", "يستاهل"),
    "gaming": ("gaming", "fps", "gpu", "ألعاب", "العاب", "كرت الشاشة"),
    "pros_cons": ("pros", "cons", "verdict", "مميزات", "عيوب", "الحكم"),
}

ASPECT_TERMS: tuple[str, ...] = tuple(
    normalize_lookup(term) for terms in ASPECT_KEYWORDS.values() for term in terms
)

VERDICT_TERMS: tuple[str, ...] = tuple(
    normalize_lookup(term)
    for term in (
        "i recommend",
        "would recommend",
        "worth it",
        "buy it",
        "avoid",
        "don't buy",
        "do not buy",
        "disappointed",
        "أنصح",
        "لا أنصح",
        "يستاهل",
        "لا يستاهل",
    )
)

SPONSOR_TERMS: tuple[str, ...] = tuple(
    normalize_lookup(term)
    for term in (
        "sponsored",
        "sponsor",
        "this video is sponsored",
        "paid promotion",
        "راعي",
        "إعلان",
        "اعلان",
    )
)

NOISE_TERMS: tuple[str, ...] = tuple(
    normalize_lookup(term)
    for term in (
        "includes mouse & bag",
        "includes mouse and bag",
        "free bag",
        "with bag",
        "windows 11",
        "windows 10",
        "special offer",
        "best seller",
        "hot deal",
    )
)
