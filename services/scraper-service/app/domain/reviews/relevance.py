"""Pure domain target-relevance, accessory/device vetoing, and target consolidation.

Zero I/O or infrastructure imports: relies only on standard-library regexes,
pure vocabulary tables, and Pydantic event schemas so every rule is
unit-testable in milliseconds.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from urllib.parse import urlparse

from app.core.classifier import ProductClassifier
from app.domain.reviews.vocabulary import (
    ARABIC_BRAND_NAMES,
    ARABIC_FAMILY_NAMES,
    BRAND_ALIASES,
    FAMILY_ALIASES,
    normalize_lookup,
)
from app.schemas.events import LaptopReviewTarget

# ─── Device, Accessory & Roundup Veto Patterns ──────────────────────────────

# Form-factor wording and laptop-only model families that prove a monitor/GPU
# mention refers to a laptop's internal display or mobile graphics.
LAPTOP_CONTEXT_PATTERN = re.compile(
    r"\b(laptop|notebook|macbook|2-in-1|convertible|chassis|ultrabook)\b|"
    r"\b(?:"
    r"strix\s+[gsx]\d{2}|"
    r"zephyrus\s+[gsm]\d{2}|"
    r"scar\s+\d{2}|"
    r"tuf\s+(?:gaming\s+)?[af]\d{2}|"
    r"nitro\s+v\s*\d{2}|"
    r"legion\s+(?:pro\s+|slim\s+pro\s+|slim\s+)?\d{1,2}|"
    r"loq\s+\d{2}|"
    r"victus\s+\d{2}|"
    r"omen\s+\d{2}|"
    r"predator\s+helios\s+\d{2}|"
    r"katana\s+\d{2}|"
    r"cyborg\s+\d{2}|"
    r"raider\s+[a-z]{2}\d{2}|"
    r"vector\s+[a-z]{2}\d{2}|"
    r"sword\s+\d{2}|"
    r"stealth\s+\d{2}"
    r")\b|"
    r"(لاب\s*توب|لابتوب|نوت\s*بوك|حاسوب\s*محمول)",
    re.IGNORECASE,
)

# Explicit external-display wording always vetoes even when a laptop sub-brand appears.
EXPLICIT_EXTERNAL_MONITOR_PATTERN = re.compile(
    r"\b(gaming\s+monitor|curved\s+monitor|portable\s+monitor|oled\s+monitor|ultrawide\s+monitor|"
    r"ips\s+monitor|smart\s+monitor|lcd\s+monitor|led\s+monitor|studio\s+display|pro\s+display)\b|"
    r"\bmonitors?\b|"
    r"(شاشة\s*(?:ألعاب|قيمنق|منحنية))",
    re.IGNORECASE,
)

# Standalone monitor model families commonly seen in review titles.
MONITOR_MODEL_PATTERN = re.compile(
    r"\b(?:vg|vx|xv|pg|mg|xg)\s?\d{2,3}[a-z0-9-]*\b",
    re.IGNORECASE,
)

# Standalone desktop GPU model naming commonly seen in review titles.
STANDALONE_GPU_PATTERN = re.compile(
    r"\b(?:geforce\s+)?(?:rtx|gtx)\s*\d{3,4}(?:\s*(?:ti|super))?\b|"
    r"\bradeon\s+(?:rx\s*)?\d{3,4}\b",
    re.IGNORECASE,
)

# Unmistakable standalone accessories that are never laptop reviews when named as subjects.
HARD_ACCESSORY_SUBJECT_PATTERN = re.compile(
    r"\b(backpack|laptop\s+bag|briefcase|sleeve|laptop\s+stand|cooling\s+pad|docking\s+station|docking|"
    r"usb\s+hub|type-c\s+hub|mousepad|mouse\s+pad|headset|earphones|headphones|earbuds|"
    r"flash\s+drive|usb\s+drive|power\s+bank|stylus\s+pen|screen\s+protector|power\s+adapter|"
    r"charger|router|extender|external\s+hard|external\s+hdd|memory\s+card|sd\s+card|microsd|"
    r"airpods|apple\s+pencil|magic\s+mouse|magsafe|"
    r"gaming\s+mouse|wireless\s+mouse|mechanical\s+keyboard|wireless\s+keyboard|gaming\s+keyboard)\b|"
    r"(حقيبة|شنطة|شنطه|جراب|حامل\s*لاب|قاعدة\s*تبريد|شاحن|ماوس\s*باد|سماعة|سماعات|فلاشة|فلاشه|راوتر)",
    re.IGNORECASE,
)

# Peripheral titles where accessory phrasing matches ProductClassifier.ACCESSORY_PATTERN
# without internal laptop keyboard/camera context (e.g. "ASUS ROG Webcam review").
_STANDALONE_PERIPHERAL_PATTERN = re.compile(
    r"\b(keyboard|mouse|webcam|microphone)\b",
    re.IGNORECASE,
)

_ROUNDUP_TITLE_RE = re.compile(
    r"^\s*(?:the\s+)?(?:\d+\s+)?best\b.*\b(?:laptops?|notebooks?|computers?|pcs?)\b",
    re.IGNORECASE,
)


def is_non_laptop_device_text(title: str, text: str = "") -> bool:
    """Return ``True`` if title/text refers to a non-laptop device, component, or accessory."""
    title_str = (title or "").strip()
    body_prefix = (text or "")[:600].strip()
    sample = f"{title_str} {body_prefix}".strip()
    if not sample:
        return False

    has_laptop_context = bool(LAPTOP_CONTEXT_PATTERN.search(sample))

    # Standalone accessory check against headline first (prevents "charging" / "backlit keyboard"
    # mentions in laptop review paragraphs from triggering false vetoes).
    if title_str:
        if HARD_ACCESSORY_SUBJECT_PATTERN.search(title_str):
            return True
        if (
            _STANDALONE_PERIPHERAL_PATTERN.search(title_str)
            and not ProductClassifier.KEYBOARD_LAYOUT_PATTERN.search(title_str)
            and not has_laptop_context
        ):
            return True

    # Also catch explicit standalone accessory subjects right at the start of body text
    # when title is generic (e.g. "Hands-on review" + body starting with accessory description).
    if body_prefix and HARD_ACCESSORY_SUBJECT_PATTERN.search(body_prefix[:180]) and not has_laptop_context:
        return True

    for cat, pat in ProductClassifier.HARD_VETO_PATTERNS:
        if not pat.search(sample):
            continue
        if cat == "monitor":
            if has_laptop_context and not EXPLICIT_EXTERNAL_MONITOR_PATTERN.search(sample):
                continue
            return True
        if cat == "gpu":
            if has_laptop_context:
                continue
            return True
        return True

    if STANDALONE_GPU_PATTERN.search(sample) and not has_laptop_context:
        return True
    if MONITOR_MODEL_PATTERN.search(sample) and not has_laptop_context:
        return True

    return False


# ─── Brand, Family & Word-Boundary Target Matching ──────────────────────────

GENERIC_MODEL_TOKENS: frozenset[str] = frozenset(
    {
        "laptop",
        "laptops",
        "notebook",
        "notebooks",
        "gaming",
        "series",
        "edition",
        "pro",
        "plus",
        "air",
        "max",
        "ultra",
        "studio",
        "book",
        "slim",
        "creator",
        "workstation",
        "core",
        "essential",
        "ai",
        "new",
        "powered",
        "review",
        "reviews",
        "hands",
        "black",
        "white",
        "silver",
        "gray",
        "grey",
        "generation",
        "gen",
        "intel",
        "amd",
        "ryzen",
        "nvidia",
        "geforce",
        "rtx",
        "gtx",
        "radeon",
        "oled",
        "ips",
        "fhd",
        "qhd",
        "wuxga",
        "wqxga",
        "inch",
        "inches",
        "pc",
        "windows",
        "win",
    }
)

# Unambiguous manufacturer-owned laptop sub-brands that safely imply brand identity.
# Unambiguous manufacturer-owned laptop sub-brands that safely imply brand identity.
# Common English words ("vector", "stealth", "titan", "modern", "prestige", "flex")
# are intentionally excluded so they always require the explicit brand name.
_OWNED_SUBBRANDS: dict[str, tuple[str, ...]] = {
    "lenovo": ("thinkpad", "ideapad", "legion", "loq"),
    "hp": ("victus", "omen", "pavilion", "elitebook", "probook", "spectre", "envy", "zbook", "omnibook"),
    "asus": ("rog", "rog strix", "zephyrus", "zenbook", "vivobook", "proart", "tuf gaming"),
    "dell": ("alienware", "xps", "inspiron", "latitude", "vostro"),
    "acer": ("predator", "nitro", "travelmate"),
    "apple": ("macbook", "macbook air", "macbook pro"),
    "msi": ("katana", "cyborg", "raider", "crosshair"),
}

# Distinct product-line names where naming a different line in the headline
# proves the review/thread covers a different chassis.
_SERIES_CONFLICT_TOKENS: frozenset[str] = frozenset(
    {
        "victus",
        "omen",
        "pavilion",
        "envy",
        "spectre",
        "elitebook",
        "probook",
        "zbook",
        "omnibook",
        "eliteboard",
        "strix",
        "scar",
        "zephyrus",
        "flow",
        "zenbook",
        "vivobook",
        "tuf",
        "proart",
        "expertbook",
        "legion",
        "loq",
        "ideapad",
        "thinkpad",
        "thinkbook",
        "yoga",
        "flex",
        "predator",
        "helios",
        "triton",
        "nitro",
        "aspire",
        "swift",
        "travelmate",
        "katana",
        "cyborg",
        "raider",
        "vector",
        "stealth",
        "prestige",
        "modern",
        "titan",
        "crosshair",
        "alienware",
        "xps",
        "latitude",
        "inspiron",
        "vostro",
    }
)

# Umbrella brand/sub-brand prefixes that may be omitted when the more specific
# series token is already named (e.g. "Strix Scar 18" vs "ROG Strix Scar 18").
_OPTIONAL_UMBRELLA_FAMILY_TOKENS: frozenset[str] = frozenset(
    {"rog", "predator", "asus", "hp", "lenovo", "acer", "msi", "dell"}
)

_HARDWARE_SPEC_CODE_RE = re.compile(
    r"^(?:RTX\d+|GTX\d+|DDR\d[A-Z]*|LPDDR\d[A-Z]*|GEN\d+|WIN\d+|USB\d+|WIFI\d+|I[3579]|R[3579]|M[1-4]|U[579])$"
)
_CODE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}")
_SIZE_IN_MODEL_RE = re.compile(r"(?<![a-z0-9])([gsx]?)(1[1-8])(?![0-9])", re.IGNORECASE)
_TITLE_SIZE_CLASS_RE = re.compile(
    r"(?<![a-z0-9])(?:[gsmx])?(1[1-8])(?:\.\d)?(?=(?:\s*(?:inch|in|\"|”|-inch|x\b))|(?:\s+(?:review|laptop|gaming|gen|oled|edition|flip|pro|slim|plus|go|ai|hdr|max|ultra|touch|202\d))|$)|"
    r"\b(?:scar|strix|victus|omen|loq|legion|vivobook|zenbook|zephyrus|helios|triton|nitro|tuf|katana|cyborg|vector|raider|stealth|omnibook|inspiron|latitude|vostro)\s+(1[1-8])\b",
    re.IGNORECASE,
)
_ROMAN_GEN_RE = re.compile(r"\b(ii|iii|iv)\b", re.IGNORECASE)


def contains_word_boundary(normalized_haystack: str, term: str) -> bool:
    """Return ``True`` when ``term`` matches on non-alphanumeric / Arabic word boundaries."""
    norm_term = normalize_lookup(term)
    if not norm_term or not normalized_haystack:
        return False
    pattern = rf"(?<![a-z0-9\u0600-\u06ff]){re.escape(norm_term)}(?![a-z0-9\u0600-\u06ff])"
    return bool(re.search(pattern, normalized_haystack))


def extract_code_tokens(values: Sequence[str | None]) -> set[str]:
    """Extract alphanumeric model/SKU code tokens (length >= 4, both letters & digits)."""
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue
        for raw in _CODE_TOKEN_RE.findall(str(value)):
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


def _canonical_brand(brand: str | None) -> str:
    norm = normalize_lookup(brand)
    if not norm:
        return ""
    return normalize_lookup(BRAND_ALIASES.get(norm, brand))


def _brand_aliases_for(brand: str | None) -> set[str]:
    canon = _canonical_brand(brand)
    if not canon:
        return set()
    aliases: set[str] = {canon}
    for alias, mapped in BRAND_ALIASES.items():
        if normalize_lookup(mapped) == canon:
            aliases.add(alias)
    for canonical_name, arabic_name in ARABIC_BRAND_NAMES.items():
        if normalize_lookup(canonical_name) == canon:
            aliases.add(normalize_lookup(arabic_name))
    aliases.update(_OWNED_SUBBRANDS.get(canon, ()))
    return {a for a in aliases if a}


def _family_matches(haystack_norm: str, target_family: str | None) -> bool:
    """Require all distinctive sub-series tokens (or an Arabic family alias) to match."""
    norm = normalize_lookup(target_family)
    if not norm:
        return False

    # Build candidate phrases (normalized raw, canonical alias, reverse aliases)
    phrases: list[str] = [norm]
    canonical = FAMILY_ALIASES.get(norm)
    if canonical:
        canon_norm = normalize_lookup(canonical)
        if canon_norm and canon_norm not in phrases:
            phrases.append(canon_norm)
    for english_fam, arabic_fam in ARABIC_FAMILY_NAMES.items():
        if normalize_lookup(english_fam) in phrases:
            ar_norm = normalize_lookup(arabic_fam)
            if ar_norm and contains_word_boundary(haystack_norm, ar_norm):
                return True

    # For Latin family phrases like "Rog Strix Scar" or "Predator Helios Neo", require every
    # non-generic sub-series token (keeping umbrella tokens like "rog"/"predator" optional).
    raw_words = [w for w in norm.split() if w and w not in GENERIC_MODEL_TOKENS]
    if not raw_words:
        return False
    required = [w for w in raw_words if w not in _OPTIONAL_UMBRELLA_FAMILY_TOKENS] or raw_words
    return all(contains_word_boundary(haystack_norm, word) for word in required)


def _has_conflicting_series_in_headline(target: LaptopReviewTarget, headline_norm: str) -> bool:
    if not headline_norm:
        return False
    target_text = normalize_lookup(
        " ".join(
            part for part in (target.brand, target.laptop_family, target.laptop_model, target.canonical_id) if part
        )
    )
    target_words = set(target_text.split())
    headline_words = set(headline_norm.split())
    for word in headline_words:
        if word in _SERIES_CONFLICT_TOKENS and word not in target_words:
            return True
    return False


def _has_conflicting_code_in_headline(
    target_codes: set[str],
    title_str: str,
    url_slug: str,
    headline_norm: str,
    target_text_norm: str,
) -> bool:
    if _ROMAN_GEN_RE.search(title_str) and not _ROMAN_GEN_RE.search(target_text_norm):
        return True
    if not target_codes:
        return False
    # Only enforce against substantial alphanumeric chassis codes (e.g. G835LX, TP3407SA).
    strong_target_codes = {c for c in target_codes if len(c) >= 5}
    if not strong_target_codes:
        return False
    if any(contains_word_boundary(headline_norm, code) for code in target_codes):
        return False

    headline_codes = {c for c in extract_code_tokens([title_str, url_slug]) if len(c) >= 4}
    for h_code in headline_codes:
        # Ignore short CPU/generation tags or display tags like "G1A", "U7", "2026"
        if any(h_code in t_code or t_code in h_code for t_code in strong_target_codes):
            return False
        # Ignore generic GPU/CPU/display prefixes caught as alnum (already mostly filtered, guard G14..G18)
        if re.fullmatch(r"[AGMSX]?1[1-8][A-Z]?", h_code):
            continue
        return True
    return False


def _target_size_class(target: LaptopReviewTarget) -> str | None:
    if target.laptop_model:
        match = _SIZE_IN_MODEL_RE.search(target.laptop_model)
        if match:
            return match.group(2)
    if target.screen_size is not None:
        size_int = int(target.screen_size)
        if 11 <= size_int <= 18:
            return str(size_int)
    return None


def _title_size_classes(title: str) -> set[str]:
    sizes: set[str] = set()
    for match in _TITLE_SIZE_CLASS_RE.finditer(title or ""):
        size = match.group(1) or match.group(2)
        if size:
            sizes.add(size)
    return sizes


def matches_target_text(
    target: LaptopReviewTarget,
    title: str,
    body: str = "",
    url: str = "",
    *,
    require_brand: bool = True,
    reject_roundups: bool = False,
    require_headline_match: bool = False,
) -> bool:
    """Return ``True`` when candidate content genuinely evaluates ``target``."""
    title_str = (title or "").strip()
    body_str = (body or "").strip()
    raw_url = (url or "").strip()
    parsed_url = urlparse(raw_url) if "://" in raw_url else None
    url_path = parsed_url.path if parsed_url is not None else raw_url
    url_slug = url_path.replace("/", " ").replace("-", " ").replace("_", " ").strip()

    if not (title_str or body_str):
        return False

    if is_non_laptop_device_text(title_str, body_str):
        return False

    norm_title = normalize_lookup(title_str)
    norm_body = normalize_lookup(body_str)
    norm_url = normalize_lookup(url_slug)
    combined_norm = " ".join(part for part in (norm_title, norm_url, norm_body) if part)
    headline_norm = " ".join(part for part in (norm_title, norm_url) if part) or norm_body
    match_scope = headline_norm if require_headline_match else combined_norm
    target_text_norm = normalize_lookup(
        " ".join(part for part in (target.brand, target.laptop_family, target.laptop_model) if part)
    )

    code_tokens = extract_code_tokens(
        [
            target.laptop_model,
            target.mpn,
            target.manufacturer_part_number,
            target.retailer_sku,
            *target.skus,
            *target.mpns,
        ]
    )

    if reject_roundups and title_str and _ROUNDUP_TITLE_RE.search(title_str):
        # Allow a roundup only if it literally references one of the target's exact model codes.
        if not any(contains_word_boundary(headline_norm, code) for code in code_tokens):
            return False

    # 1. Brand check (strict word boundary against aliases or unambiguous sub-brands).
    if require_brand and target.brand:
        aliases = _brand_aliases_for(target.brand)
        if aliases and not any(contains_word_boundary(match_scope, alias) for alias in aliases):
            return False

    # 2. Check exact model/SKU code hit on word boundaries.
    compact_haystack = re.sub(r"[^a-z0-9]", "", match_scope)
    matched_code = False
    for code in code_tokens:
        if contains_word_boundary(match_scope, code):
            matched_code = True
            break
        compact_code = re.sub(r"[^a-z0-9]", "", code.lower())
        if len(compact_code) >= 5 and compact_code in compact_haystack:
            matched_code = True
            break

    # 3. Reject headlines that explicitly reference a conflicting sub-series, chassis code, or screen size.
    exact_code_in_title = any(contains_word_boundary(headline_norm, code) for code in code_tokens)
    if headline_norm and not exact_code_in_title:
        if _has_conflicting_series_in_headline(target, headline_norm):
            return False
        if require_headline_match and _has_conflicting_code_in_headline(
            code_tokens, title_str, url_slug, headline_norm, target_text_norm
        ):
            return False

    target_size = _target_size_class(target)
    if target_size and title_str:
        title_sizes = _title_size_classes(title_str)
        if title_sizes and target_size not in title_sizes and not exact_code_in_title:
            return False

    if matched_code:
        return True

    # 4. Distinctive family match (requires all core sub-series tokens, not arbitrary fragments).
    if _family_matches(match_scope, target.laptop_family):
        return True

    # 5. Distinctive non-generic words from laptop_model when family was generic/missing.
    if target.laptop_model:
        family_words = {
            w for w in normalize_lookup(target.laptop_family).split() if w and w not in GENERIC_MODEL_TOKENS
        }
        if not family_words:
            model_words = [
                w
                for w in normalize_lookup(target.laptop_model).split()
                if len(w) >= 3 and not w.isdigit() and w not in GENERIC_MODEL_TOKENS
            ]
            brand_canon = _canonical_brand(target.brand)
            distinct_words = [w for w in model_words if w != brand_canon and w not in _OPTIONAL_UMBRELLA_FAMILY_TOKENS]
            if distinct_words and any(contains_word_boundary(match_scope, w) for w in distinct_words):
                return True

    return False


# ─── Batch Target Consolidation by Chassis Key ──────────────────────────────


def _default_chassis_key(target: LaptopReviewTarget) -> str:
    explicit = str(getattr(target, "chassis_key", None) or "").strip()
    if explicit:
        return explicit

    def _norm(val: str | None) -> str | None:
        if not val:
            return None
        cleaned = re.sub(r"[^a-z0-9]+", "-", str(val).strip().lower()).strip("-")
        return cleaned or None

    brand = _norm(target.brand)
    family = _norm(target.laptop_family)
    model = _norm(target.laptop_model)
    if model and family and model.startswith(f"{family}-"):
        model = model[len(family) + 1 :]
    parts = [p for p in (brand, family, model) if p]
    return ":".join(parts) if parts else str(target.canonical_id).strip().lower()


def _dedupe_extend(dest: list[str], items: Sequence[str | None]) -> None:
    seen = set(dest)
    for item in items:
        if not item:
            continue
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            dest.append(cleaned)


def consolidate_targets_by_chassis(
    targets: Sequence[LaptopReviewTarget],
    key_fn: Callable[[LaptopReviewTarget], str] = _default_chassis_key,
) -> list[LaptopReviewTarget]:
    """Group colliding ``LaptopReviewTarget`` items sharing one ``chassis_key``.

    Preserves input order while merging ``matched_laptop_ids``,
    ``matched_canonical_ids``, ``skus``, ``mpns``, and ``product_urls`` so
    downstream collectors neither scrape duplicate work nor silently overwrite
    entries inside ``dict[chassis_key, ...]``.
    """
    grouped: dict[str, list[LaptopReviewTarget]] = {}
    for target in targets or ():
        key = key_fn(target)
        grouped.setdefault(key, []).append(target)

    consolidated: list[LaptopReviewTarget] = []
    for key, members in grouped.items():
        if len(members) == 1:
            single = members[0]
            if not single.chassis_key:
                single = single.model_copy(update={"chassis_key": key})
            consolidated.append(single)
            continue

        # Pick the richest representative for metadata while merging all variant IDs.
        rep = max(
            members,
            key=lambda m: (
                bool(m.title),
                len(m.laptop_model or ""),
                bool(m.screen_size),
                bool(m.mpn),
            ),
        )
        matched_laptop_ids: list[str] = []
        matched_canonical_ids: list[str] = []
        skus: list[str] = []
        mpns: list[str] = []
        product_urls: list[str] = []

        for member in members:
            _dedupe_extend(matched_laptop_ids, member.matched_laptop_ids or [member.laptop_id])
            _dedupe_extend(matched_canonical_ids, member.matched_canonical_ids or [member.canonical_id])
            _dedupe_extend(skus, [member.retailer_sku, *member.skus])
            _dedupe_extend(mpns, [member.mpn, member.manufacturer_part_number, *member.mpns])
            _dedupe_extend(product_urls, member.product_urls)

        screen_size = next((m.screen_size for m in members if m.screen_size is not None), None)
        thumbnail_url = next((m.thumbnail_url for m in members if m.thumbnail_url), None)

        consolidated.append(
            rep.model_copy(
                update={
                    "chassis_key": key,
                    "matched_laptop_ids": matched_laptop_ids,
                    "matched_canonical_ids": matched_canonical_ids,
                    "skus": skus,
                    "mpns": mpns,
                    "product_urls": product_urls,
                    "screen_size": rep.screen_size if rep.screen_size is not None else screen_size,
                    "thumbnail_url": rep.thumbnail_url or thumbnail_url,
                }
            )
        )

    return consolidated


__all__ = [
    "GENERIC_MODEL_TOKENS",
    "consolidate_targets_by_chassis",
    "contains_word_boundary",
    "extract_code_tokens",
    "is_non_laptop_device_text",
    "matches_target_text",
]
