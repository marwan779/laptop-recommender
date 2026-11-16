"""Pure review-source relevance bouncer for S3/JSON catalog dumps.

This module mirrors the scraper-service relevance policy without importing any
infrastructure, ML, HTTP, or database code. It only inspects in-memory dicts and
returns ``(is_relevant, reason)`` so callers can explain why an entry was
dropped before it reaches prompts, embeddings, or ``review_sources``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

# ─── Vocabulary ─────────────────────────────────────────────────────────────

GENERIC_MODEL_TOKENS: Set[str] = {
    "laptop", "laptops", "notebook", "notebooks", "gaming", "series", "edition",
    "pro", "plus", "air", "max", "ultra", "studio", "book", "slim", "creator",
    "workstation", "core", "essential", "ai", "new", "powered", "review",
    "reviews", "hands", "black", "white", "silver", "gray", "grey", "generation",
    "gen", "intel", "amd", "ryzen", "nvidia", "geforce", "rtx", "gtx", "radeon",
    "oled", "ips", "fhd", "qhd", "wuxga", "wqxga", "inch", "inches", "pc",
    "windows", "win",
}

_OPTIONAL_UMBRELLA_FAMILY_TOKENS: Set[str] = {
    "rog", "predator", "asus", "hp", "lenovo", "acer", "msi", "dell",
}

_OWNED_SUBBRANDS: Dict[str, Tuple[str, ...]] = {
    "lenovo": ("thinkpad", "ideapad", "legion", "loq"),
    "hp": ("victus", "omen", "pavilion", "elitebook", "probook", "spectre", "envy", "zbook", "omnibook"),
    "asus": ("rog", "rog strix", "zephyrus", "zenbook", "vivobook", "proart", "tuf gaming", "tuf"),
    "dell": ("alienware", "xps", "inspiron", "latitude", "vostro"),
    "acer": ("predator", "nitro", "travelmate"),
    "apple": ("macbook", "macbook air", "macbook pro"),
    "msi": ("katana", "cyborg", "raider", "crosshair"),
}

_BRAND_ALIASES: Dict[str, str] = {
    "asus": "asus",
    "اسوس": "asus",
    "أسوس": "asus",
    "hp": "hp",
    "hewlett packard": "hp",
    "اتش بي": "hp",
    "إتش بي": "hp",
    "lenovo": "lenovo",
    "لينوفو": "lenovo",
    "dell": "dell",
    "ديل": "dell",
    "acer": "acer",
    "ايسر": "acer",
    "إيسر": "acer",
    "apple": "apple",
    "ابل": "apple",
    "أبل": "apple",
    "msi": "msi",
    "ام اس اي": "msi",
    "إم إس آي": "msi",
    "gigabyte": "gigabyte",
    "جيجابايت": "gigabyte",
    "huawei": "huawei",
    "هواوي": "huawei",
    "xiaomi": "xiaomi",
    "شاومي": "xiaomi",
    "redmi": "redmi",
    "ريدمي": "redmi",
    "realme": "realme",
    "ريلمي": "realme",
    "samsung": "samsung",
    "سامسونج": "samsung",
    "microsoft": "microsoft",
    "مايكروسوفت": "microsoft",
    "razer": "razer",
    "ريزر": "razer",
    "alienware": "alienware",
    "الينوير": "alienware",
    "infinix": "infinix",
    "tecno": "tecno",
    "toshiba": "toshiba",
    "توشيبا": "toshiba",
    "sony": "sony",
    "سوني": "sony",
}

_SERIES_CONFLICT_TOKENS: Set[str] = {
    "victus", "omen", "pavilion", "envy", "spectre", "elitebook", "probook",
    "zbook", "omnibook", "eliteboard", "strix", "scar", "zephyrus", "flow",
    "zenbook", "vivobook", "tuf", "proart", "expertbook", "legion", "loq",
    "ideapad", "thinkpad", "thinkbook", "yoga", "flex", "predator", "helios",
    "triton", "nitro", "aspire", "swift", "travelmate", "katana", "cyborg",
    "raider", "vector", "stealth", "prestige", "modern", "titan", "crosshair",
    "alienware", "xps", "latitude", "inspiron", "vostro",
}

# ─── Noise / device veto patterns ───────────────────────────────────────────

_LAPTOP_CONTEXT_RE = re.compile(
    r"\b(laptop|notebook|macbook|2-in-1|convertible|chassis|ultrabook)\b|"
    r"\b(?:strix\s+[gsx]\d{2}|zephyrus\s+[gsm]\d{2}|scar\s+\d{2}|tuf\s+(?:gaming\s+)?[af]\d{2}|"
    r"nitro\s+v\s*\d{2}|legion\s+(?:pro\s+|slim\s+pro\s+|slim\s+)?\d{1,2}|loq\s+\d{2}|"
    r"victus\s+\d{2}|omen\s+\d{2}|predator\s+helios\s+\d{2}|katana\s+\d{2}|cyborg\s+\d{2}|"
    r"raider\s+[a-z]{2}\d{2}|vector\s+[a-z]{2}\d{2}|sword\s+\d{2}|stealth\s+\d{2})\b|"
    r"(لاب\s*توب|لابتوب|نوت\s*بوك|حاسوب\s*محمول)",
    re.IGNORECASE,
)
_EXPLICIT_EXTERNAL_MONITOR_RE = re.compile(
    r"\b(gaming\s+monitor|curved\s+monitor|portable\s+monitor|oled\s+monitor|ultrawide\s+monitor|"
    r"ips\s+monitor|smart\s+monitor|lcd\s+monitor|led\s+monitor|studio\s+display|pro\s+display)\b|"
    r"\bmonitors?\b|(شاشة\s*(?:ألعاب|قيمنق|منحنية))",
    re.IGNORECASE,
)
_MONITOR_MODEL_RE = re.compile(r"\b(?:vg|vx|xv|pg|mg|xg)\s?\d{2,3}[a-z0-9-]*\b", re.IGNORECASE)
_STANDALONE_GPU_RE = re.compile(
    r"\b(?:geforce\s+)?(?:rtx|gtx)\s*\d{3,4}(?:\s*(?:ti|super))?\b|"
    r"\bradeon\s+(?:rx\s*)?\d{3,4}\b",
    re.IGNORECASE,
)
_ACCESSORY_RE = re.compile(
    r"\b(backpack|laptop\s+bag|briefcase|sleeve|laptop\s+stand|cooling\s+pad|docking\s+station|docking|"
    r"usb\s+hub|type-c\s+hub|mousepad|mouse\s+pad|headset|earphones|headphones|earbuds|"
    r"flash\s+drive|usb\s+drive|power\s+bank|stylus\s+pen|screen\s+protector|power\s+adapter|"
    r"charger|router|extender|external\s+hard|external\s+hdd|memory\s+card|sd\s+card|microsd|"
    r"airpods|apple\s+pencil|magic\s+mouse|magsafe|gaming\s+mouse|wireless\s+mouse|"
    r"mechanical\s+keyboard|wireless\s+keyboard|gaming\s+keyboard)\b|"
    r"(حقيبة|شنطة|شنطه|جراب|حامل\s*لاب|قاعدة\s*تبريد|شاحن|ماوس\s*باد|سماعة|سماعات|فلاشة|فلاشه|راوتر)",
    re.IGNORECASE,
)
_DESKTOP_BUILD_RE = re.compile(
    r"\b(?:b550|b650e?|x570|x670e?|z890|z790|b760|b860|x870e?|a620|h610)[a-z0-9-]*\b|"
    r"\b(?:bios\s+raid|vfio|pcie\s+passthrough|iommu\s+passthrough)\b|"
    r"\b(?:motherboard|mainboard|mobo)\b|"
    r"\b(?:graphics\s+card|video\s+card|desktop\s+(?:pc|gpu|build)|gaming\s+desktop|tower\s+pc)\b",
    re.IGNORECASE,
)
_HANDHELD_OR_WEARABLE_RE = re.compile(
    r"\b(?:legion\s+go(\s+s)?|rog\s+ally(\s+x)?|steam\s+deck|smart\s+glasses|ar\s+glasses|vr\s+headset)\b|(نظارات)",
    re.IGNORECASE,
)
_ARABIC_PROMO_RE = re.compile(r"(مسابقة|اربح|معرض|تسريب|نظارات|شاشة)")
_POSITIVE_REVIEW_SIGNAL_RE = re.compile(
    r"(?:#\s*review|hands-on\s+review|\btesting\b|pros\s+and\s+cons|مراجعة|تجربة|تقييم|اختبار)",
    re.IGNORECASE,
)
_ROUNDUP_TITLE_RE = re.compile(
    r"^\s*(?:the\s+)?(?:\d+\s+)?best\b.*\b(?:laptops?|notebooks?|computers?|pcs?)\b|"
    r"\b(?:roundup|best\s+laptops?)\b",
    re.IGNORECASE,
)
_MEGATHREAD_RE = re.compile(r"\b(?:mega\s*thread|megathread|owners?\s+thread)\b", re.IGNORECASE)
_SUPPORT_OR_ADVICE_RE = re.compile(
    r"\b(?:looking\s+for\s+(?:a\s+)?new\s+laptop|need\s+(?:a\s+)?new\s+laptop|"
    r"which\s+laptop\s+should\s+i\s+get|should\s+i\s+buy|advice\s+for\s+buying|"
    r"in\s+the\s+market\s+for|recommend\s+me|please\s+help|pls\s+help|"
    r"compatible\s+ram|ram\s+upgrade|fatal\s+trackpad\s+issue|tpm\s+bios\s+problem|"
    r"freezes\s+on\s+linux|kernel\s+panic|how\s+to\s+limit\s+charging|"
    r"display\s+upgrade|external\s+gpu\s+for|wmic|lspci|dual\s+boot)\b",
    re.IGNORECASE,
)
_TITLE_REVIEW_WORD_RE = re.compile(r"\breview\b", re.IGNORECASE)
_TITLE_HELP_OR_ADVICE_RE = re.compile(r"\b(?:looking\s+for|which\s+laptop|advice|help)\b", re.IGNORECASE)
_SYNTHESIZED_MARKERS: Tuple[str, ...] = ("[Synthesized from", "AI_CHASSIS_SYNTHESIS_FALLBACK")

_HPE_COLLISION_RE = re.compile(r"\bhpe\b|\bisocell\s+hp\d+\b", re.IGNORECASE)
_THREE_D_PRINTING_RE = re.compile(
    r"\b(?:3d\s*print(?:ing|er|ed)?|garolite|fr4|filament|resin\s*print(?:ing)?)\b",
    re.IGNORECASE,
)

# ─── Code / size patterns ───────────────────────────────────────────────────

_HARDWARE_SPEC_CODE_RE = re.compile(
    r"^(?:RTX\d+|GTX\d+|DDR\d[A-Z]*|LPDDR\d[A-Z]*|GEN\d+|WIN\d+|USB\d+|WIFI\d+|I[3579]|R[3579]|M[1-4]|U[579])$"
)
_CODE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}")
_CHASSIS_ROOT_RE = re.compile(r"^([A-Za-z]+\d+)")
_CPU_SUFFIX_CODE_RE = re.compile(r"(?<![a-z0-9])(\d{3,4})(?:hx?|u|v|k)(?![a-z0-9])")
_SIZE_IN_MODEL_RE = re.compile(r"(?<![a-z0-9])([gsx]?)(1[1-8])(?![0-9])", re.IGNORECASE)
_TITLE_SIZE_RE = re.compile(
    r"(?<![a-z0-9])(?:[agmsvx])?(1[1-8])(?:\.\d)?(?=(?:\s*(?:inch|in|\"|”|-inch|x\b))|"
    r"(?:\s+(?:review|laptop|gaming|gen|oled|edition|flip|pro|slim|plus|go|ai|hdr|max|ultra|touch|202\d))|$)|"
    r"\b(?:scar|strix|victus|omen|loq|legion|vivobook|zenbook|zephyrus|helios|triton|nitro|tuf|katana|"
    r"cyborg|vector|raider|stealth|omnibook|inspiron|latitude|vostro)\s+(1[1-8])\b",
    re.IGNORECASE,
)

# ─── Text helpers ───────────────────────────────────────────────────────────


def _normalize(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[\s\-_/]+", " ", text)
    return text.strip()


def _slug_text(url: str) -> str:
    try:
        path = urlparse(url or "").path
    except ValueError:
        path = ""
    return _normalize(unquote(path).replace("/", " ").replace(".", " "))


def _contains(haystack: str, term: str) -> bool:
    norm_term = _normalize(term)
    if not norm_term or not haystack:
        return False
    pattern = rf"(?<![a-z0-9\u0600-\u06ff]){re.escape(norm_term)}(?![a-z0-9\u0600-\u06ff])"
    return bool(re.search(pattern, haystack))


def _canonical_brand(brand: Any) -> str:
    norm = _normalize(brand)
    if not norm:
        return ""
    return _BRAND_ALIASES.get(norm, norm)


def _brand_aliases(brand: Any) -> Set[str]:
    canon = _canonical_brand(brand)
    if not canon:
        return set()
    aliases = {canon}
    aliases.update(alias for alias, mapped in _BRAND_ALIASES.items() if mapped == canon)
    aliases.update(_OWNED_SUBBRANDS.get(canon, ()))
    return {_normalize(alias) for alias in aliases if _normalize(alias)}


def _extract_codes(values: Iterable[Any]) -> Set[str]:
    tokens: Set[str] = set()
    for value in values:
        for raw in _CODE_TOKEN_RE.findall(str(value or "")):
            token = raw.upper().strip("-")
            if len(token) < 4:
                continue
            if not (any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token)):
                continue
            if _HARDWARE_SPEC_CODE_RE.match(token):
                continue
            tokens.add(token)
            if "-" in token:
                for part in token.split("-"):
                    part = part.strip()
                    if (
                        len(part) >= 4
                        and any(ch.isdigit() for ch in part)
                        and any(ch.isalpha() for ch in part)
                        and not _HARDWARE_SPEC_CODE_RE.match(part)
                    ):
                        tokens.add(part)
    return tokens


def _chassis_root(code: str) -> str:
    match = _CHASSIS_ROOT_RE.match(str(code or "").strip().upper())
    if not match:
        return ""
    root = match.group(1)
    return root if len(root) >= 4 else ""


def _target_size(identity: Dict[str, Any], screen_size: Optional[float]) -> Optional[str]:
    if screen_size is not None:
        try:
            size = int(float(screen_size))
        except (TypeError, ValueError):
            size = 0
        if 11 <= size <= 18:
            return str(size)
    model = identity.get("laptop_model")
    if model:
        match = _SIZE_IN_MODEL_RE.search(str(model))
        if match:
            return match.group(2)
    return None


def _title_sizes(text: str) -> Set[str]:
    sizes: Set[str] = set()
    for match in _TITLE_SIZE_RE.finditer(text or ""):
        size = match.group(1) or match.group(2)
        if size:
            sizes.add(size)
    return sizes


def _numeric_tokens(identity: Dict[str, Any]) -> Set[str]:
    tokens: Set[str] = set()
    for value in (identity.get("laptop_family"), identity.get("laptop_model")):
        for token in _normalize(value).split():
            match = re.fullmatch(r"(\d{3,4})(?:[a-z]{0,3})?", token)
            if match:
                tokens.add(match.group(1))
    return tokens


def _identity_usable(identity: Dict[str, Any]) -> bool:
    return any(
        _normalize(identity.get(key))
        for key in ("brand", "laptop_family", "laptop_model")
    )


def _family_required_tokens(identity: Dict[str, Any]) -> List[str]:
    family_words = [
        word
        for word in _normalize(identity.get("laptop_family")).split()
        if word and word not in GENERIC_MODEL_TOKENS
    ]
    if family_words:
        required = [word for word in family_words if word not in _OPTIONAL_UMBRELLA_FAMILY_TOKENS]
        # Single-letter variant markers (Nitro V, Vivobook S, ...) are optional;
        # the distinctive family token is enough and size/series checks still run.
        distinctive = [word for word in required if len(word) >= 2]
        return distinctive or required or family_words
    brand = _canonical_brand(identity.get("brand"))
    model_words = [
        word
        for word in _normalize(identity.get("laptop_model")).split()
        if len(word) >= 3 and not word.isdigit() and word not in GENERIC_MODEL_TOKENS and word != brand
    ]
    return model_words


def _has_identity_match(identity: Dict[str, Any], headline: str) -> bool:
    brand = str(identity.get("brand") or "").strip()
    if brand:
        aliases = _brand_aliases(brand)
        if aliases and not any(_contains(headline, alias) for alias in aliases):
            return False

    required = _family_required_tokens(identity)
    if required and not any(_contains(headline, token) for token in required):
        return False
    return True


def _support_or_advice(title: str, body: str = "") -> bool:
    title_str = title or ""
    sample = f"{title_str}\n{body or ''}".strip()
    if not sample:
        return False
    if _TITLE_REVIEW_WORD_RE.search(title_str) and not _TITLE_HELP_OR_ADVICE_RE.search(title_str):
        return False
    if _POSITIVE_REVIEW_SIGNAL_RE.search(sample):
        return False
    return bool(_SUPPORT_OR_ADVICE_RE.search(sample))


def _has_code_conflict(identity: Dict[str, Any], headline: str, url_text: str) -> bool:
    target_codes = _extract_codes(
        [identity.get("laptop_model"), identity.get("laptop_family")]
    )
    strong_target_codes = {code for code in target_codes if len(code) >= 5}
    if not strong_target_codes:
        return False
    if any(_contains(headline, code) for code in target_codes):
        return False

    headline_codes = {code for code in _extract_codes([headline, url_text]) if len(code) >= 4}
    for headline_code in headline_codes:
        if any(headline_code in target or target in headline_code for target in strong_target_codes):
            return False
        headline_root = _chassis_root(headline_code)
        if headline_root and any(_chassis_root(target) == headline_root for target in strong_target_codes):
            return False
        if re.fullmatch(r"[AGMSX]?1[1-8][A-Z]?", headline_code):
            continue
        return True
    return False


def _has_numeric_collision(identity: Dict[str, Any], headline: str) -> bool:
    if _canonical_brand(identity.get("brand")) == "hp" and _HPE_COLLISION_RE.search(headline):
        return True

    identity_words = set(
        _normalize(
            " ".join(
                str(part)
                for part in (identity.get("laptop_family"), identity.get("laptop_model"))
                if part
            )
        ).split()
    )
    if "g10" in identity_words and _THREE_D_PRINTING_RE.search(headline):
        return True

    numeric_tokens = _numeric_tokens(identity)
    standalone = {token for token in numeric_tokens if _contains(headline, token)}
    for match in _CPU_SUFFIX_CODE_RE.finditer(headline):
        if match.group(1) in numeric_tokens and match.group(1) not in standalone:
            return True
    return False


def _series_conflict(identity: Dict[str, Any], headline: str) -> bool:
    target_words = set(
        _normalize(
            " ".join(
                str(part)
                for part in (
                    identity.get("brand"),
                    identity.get("laptop_family"),
                    identity.get("laptop_model"),
                )
                if part
            )
        ).split()
    )
    return any(
        word in _SERIES_CONFLICT_TOKENS and word not in target_words
        for word in headline.split()
    )


def _noise_reason(headline: str, body: str, *, platform: str, url: str) -> Optional[str]:
    combined = f"{headline} {body[:600]}".strip()
    has_laptop_context = bool(_LAPTOP_CONTEXT_RE.search(combined))

    if _HANDHELD_OR_WEARABLE_RE.search(headline):
        return "handheld_or_wearable"
    if _DESKTOP_BUILD_RE.search(headline) and not has_laptop_context:
        return "desktop_build"
    if _DESKTOP_BUILD_RE.search(body[:300]) and not has_laptop_context:
        return "desktop_build_body"
    if _ACCESSORY_RE.search(headline) and not has_laptop_context:
        return "accessory_subject"
    if _EXPLICIT_EXTERNAL_MONITOR_RE.search(headline) and not has_laptop_context:
        return "monitor_subject"
    if _MONITOR_MODEL_RE.search(headline) and not has_laptop_context:
        return "monitor_model"
    if _STANDALONE_GPU_RE.search(headline) and not has_laptop_context:
        return "standalone_gpu"
    if _THREE_D_PRINTING_RE.search(headline):
        return "three_d_printing"
    if _MEGATHREAD_RE.search(headline):
        return "megathread"

    if _ARABIC_PROMO_RE.search(headline):
        if not (has_laptop_context and _POSITIVE_REVIEW_SIGNAL_RE.search(combined)):
            return "arabic_promo_or_launch"

    if _support_or_advice(headline, body):
        return "support_or_buying_advice"

    if platform == "laptopmag" or "laptopmag.com" in url.lower():
        if _ROUNDUP_TITLE_RE.search(headline):
            return "laptopmag_roundup"
        path = urlparse(url or "").path.lower()
        if any(fragment in path for fragment in ("/news", "/deals", "/search", "/tag/", "/author/", "/category/")):
            return "laptopmag_non_review_path"
        if path in ("/reviews", "/reviews/", "/laptops/reviews", "/laptops/reviews/", "/reviews/all"):
            return "laptopmag_hub_path"
        is_review_path = (
            path.startswith("/reviews/")
            or path.endswith("-review")
            or "-review-" in path
            or "/review/" in path
        )
        if path and not is_review_path:
            return "laptopmag_non_review_path"

    return None


def _finish(
    identity: Dict[str, Any],
    headline: str,
    body: str,
    *,
    platform: str,
    url: str,
    screen_size: Optional[float],
) -> Tuple[bool, str]:
    if not _identity_usable(identity):
        return True, "identity_missing_fail_open"

    noise = _noise_reason(headline, body, platform=platform, url=url)
    if noise:
        return False, noise

    if not _has_identity_match(identity, headline):
        return False, "brand_or_family_mismatch"

    if _has_numeric_collision(identity, headline):
        return False, "numeric_or_short_token_collision"

    if _series_conflict(identity, headline):
        return False, "subseries_conflict"

    if _has_code_conflict(identity, headline, _slug_text(url)):
        return False, "chassis_code_conflict"

    target_size = _target_size(identity, screen_size)
    sizes = _title_sizes(headline)
    if target_size and sizes and target_size not in sizes:
        return False, "screen_size_mismatch"

    return True, "ok"


# ─── Public bouncer API ─────────────────────────────────────────────────────


def is_relevant_community_post(
    post: dict,
    identity: dict,
    *,
    screen_size: Optional[float] = None,
) -> Tuple[bool, str]:
    """Return whether a community/forum post is genuine evidence for ``identity``."""
    ident = identity if isinstance(identity, dict) else {}
    title = str(post.get("post_title") or post.get("title") or post.get("headline") or "").strip()
    body = str(
        post.get("post_body")
        or post.get("selftext")
        or post.get("body")
        or post.get("text")
        or post.get("content")
        or post.get("article_body")
        or ""
    ).strip()
    url = str(post.get("post_url") or post.get("url") or "").strip()
    platform = str(post.get("platform") or "").strip().lower()
    headline = f"{_normalize(title)} {_slug_text(url)}".strip()

    if not (title or body or url):
        return False, "empty_post"

    # Level1Techs OP-only policy.
    if platform == "level1techs" or "forum.level1techs.com" in url.lower():
        post_number = post.get("post_number")
        if post_number is not None and str(post_number).strip() != "1":
            return False, "level1techs_reply_post_number"
        match = re.search(r"/t/[^/]+/\d+/(\d+)/?$", url or "")
        if match and int(match.group(1)) > 1:
            return False, "level1techs_reply_url"

    # Arabhardware strictly editorial review paths.
    if platform == "arabhardware" or "arabhardware.net" in url.lower():
        path = urlparse(url or "").path.lower()
        if path and "/reviews/" not in path:
            return False, "arabhardware_non_review_path"

    return _finish(
        ident,
        headline,
        body,
        platform=platform,
        url=url,
        screen_size=screen_size,
    )


def is_relevant_editorial_review(
    ed: dict,
    identity: dict,
    *,
    screen_size: Optional[float] = None,
) -> Tuple[bool, str]:
    """Return whether an editorial review record is genuine evidence."""
    ident = identity if isinstance(identity, dict) else {}
    title = str(ed.get("post_title") or ed.get("title") or ed.get("headline") or "").strip()
    url = str(ed.get("review_url") or ed.get("url") or "").strip()
    platform = str(ed.get("source") or ed.get("platform") or "").strip().lower()
    body_parts = [
        str(ed.get("verdict") or "").strip(),
        *[str(x).strip() for x in (ed.get("pros") or []) if str(x).strip()],
        *[str(x).strip() for x in (ed.get("cons") or []) if str(x).strip()],
    ]
    body = " ".join(part for part in body_parts if part).strip()
    headline = f"{_normalize(title)} {_slug_text(url)}".strip()

    if not (title or url or body):
        return False, "empty_editorial"

    if platform == "arabhardware" or "arabhardware.net" in url.lower():
        path = urlparse(url or "").path.lower()
        if path and "/reviews/" not in path:
            return False, "arabhardware_non_review_path"

    if platform == "laptopmag" or "laptopmag.com" in url.lower():
        path = urlparse(url or "").path.lower()
        if not path or path in ("/reviews", "/reviews/", "/laptops/reviews", "/laptops/reviews/", "/reviews/all"):
            return False, "laptopmag_hub_or_empty_path"
        if any(fragment in path for fragment in ("/news", "/deals", "/search", "/tag/", "/author/", "/category/")):
            return False, "laptopmag_non_review_path"
        is_review_path = (
            path.startswith("/reviews/")
            or path.endswith("-review")
            or "-review-" in path
            or "/review/" in path
        )
        if not is_review_path:
            return False, "laptopmag_non_review_path"

    return _finish(
        ident,
        headline,
        body,
        platform=platform,
        url=url,
        screen_size=screen_size,
    )


def is_relevant_youtube_video(
    vid: dict,
    identity: dict,
    *,
    screen_size: Optional[float] = None,
) -> Tuple[bool, str]:
    """Return whether a YouTube result is a real review of ``identity``."""
    ident = identity if isinstance(identity, dict) else {}
    title = str(vid.get("title") or "").strip()
    url = str(vid.get("video_url") or vid.get("url") or "").strip()
    transcript = str(vid.get("transcript_text") or "").strip()
    transcript_source = str(vid.get("transcript_source") or vid.get("status") or "").strip()

    if (
        transcript_source == "AI_CHASSIS_SYNTHESIS_FALLBACK"
        or any(transcript.startswith(marker) for marker in _SYNTHESIZED_MARKERS)
    ):
        return False, "synthesized_fallback"

    if not title:
        return False, "youtube_missing_title"

    # Channel names are deliberately excluded from headline matching.
    headline = f"{_normalize(title)} {_slug_text(url)}".strip()
    return _finish(
        ident,
        headline,
        transcript[:600],
        platform="youtube",
        url=url,
        screen_size=screen_size,
    )


def is_relevant_review_source_entry(
    entry: dict,
    identity: dict,
    *,
    screen_size: Optional[float] = None,
) -> Tuple[bool, str]:
    """Return whether a pre-populated compact ``review_sources`` entry is valid."""
    ident = identity if isinstance(identity, dict) else {}
    title = str(entry.get("title") or "").strip()
    url = str(entry.get("url") or entry.get("review_url") or entry.get("video_url") or "").strip()
    platform = str(entry.get("platform") or "").strip().lower()
    source_type = str(entry.get("source_type") or "").strip().lower()
    headline = f"{_normalize(title)} {_slug_text(url)}".strip()

    if not (title or url):
        return False, "empty_review_source"

    if source_type == "youtube" or platform == "youtube":
        if "synthesized" in title.lower():
            return False, "synthesized_fallback"

    if platform == "arabhardware" or "arabhardware.net" in url.lower():
        path = urlparse(url or "").path.lower()
        if path and "/reviews/" not in path:
            return False, "arabhardware_non_review_path"

    if platform == "level1techs" or "forum.level1techs.com" in url.lower():
        match = re.search(r"/t/[^/]+/\d+/(\d+)/?$", url or "")
        if match and int(match.group(1)) > 1:
            return False, "level1techs_reply_url"

    return _finish(
        ident,
        headline,
        "",
        platform=platform,
        url=url,
        screen_size=screen_size,
    )


__all__ = [
    "is_relevant_community_post",
    "is_relevant_editorial_review",
    "is_relevant_review_source_entry",
    "is_relevant_youtube_video",
]
