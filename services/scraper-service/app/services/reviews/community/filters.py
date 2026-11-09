"""Pure relevance filters shared by community platform scrapers.

Extracted so forum scrapers apply the same deal-listing rule without copying
the pattern table (Single Responsibility, Open/Closed). No I/O.
"""

from __future__ import annotations

import re

from app.core.classifier import ProductClassifier

# Keywords indicating a deal/sale listing rather than a discussion.
NEGATIVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\[deal\]",
        r"\bdeals?\b",
        r"\bsale\b",
        r"\bfor sale\b",
        r"\bdiscount",
        r"\bcoupons?\b",
        r"\bpromo(?:\s*code)?\b",
        r"\bvouchers?\b",
        r"\bclearance\b",
        r"\bblack friday\b",
        r"\bcyber monday\b",
        r"\bprice drop\b",
        r"\blowest price\b",
        r"\b(?:wts|wtb|fs)\b",
        r"\bbuy(?:ing)? now\b",
    )
)

MIN_DISCUSSION_LENGTH = 40

_CODE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}")

# Form-factor wording and laptop-only model families that prove a monitor/GPU
# mention is about a laptop's internal display or mobile graphics. Bare brand
# sub-brands (TUF, ROG, Nitro, ...) are deliberately excluded because they are
# also used on desktop components.
_LAPTOP_CONTEXT_PATTERN = re.compile(
    r"\b(laptop|notebook|macbook|2-in-1|convertible|chassis)\b|"
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

# Explicit external-display wording always vetoes, even when a laptop brand is
# present (e.g. "Acer Nitro XV271U 27-inch Gaming Monitor").
_EXPLICIT_EXTERNAL_MONITOR_PATTERN = re.compile(
    r"\b(gaming\s+monitor|curved\s+monitor|portable\s+monitor|oled\s+monitor|ultrawide\s+monitor|"
    r"ips\s+monitor|smart\s+monitor|lcd\s+monitor|led\s+monitor|studio\s+display|pro\s+display)\b|"
    r"\bmonitors?\b",
    re.IGNORECASE,
)

# Standalone monitor model families commonly found in review titles.
_MONITOR_MODEL_PATTERN = re.compile(
    r"\b(?:vg|vx|xv|pg|mg|xg)\s?\d{2,3}[a-z0-9-]*\b",
    re.IGNORECASE,
)

# Standalone desktop GPU model naming commonly found in review titles.
_STANDALONE_GPU_PATTERN = re.compile(
    r"\b(?:geforce\s+)?(?:rtx|gtx)\s*\d{3,4}(?:\s*(?:ti|super))?\b|"
    r"\bradeon\s+(?:rx\s*)?\d{3,4}\b",
    re.IGNORECASE,
)


def is_deal_listing(text: str) -> bool:
    """Return ``True`` when the text looks like a deal/sale listing."""
    haystack = (text or "").lower()
    return any(pattern.search(haystack) for pattern in NEGATIVE_PATTERNS)


def is_substantive(text: str, min_length: int = MIN_DISCUSSION_LENGTH) -> bool:
    """Return ``True`` when a post body carries enough content to matter."""
    return len((text or "").strip()) >= min_length


def is_non_laptop_device(title: str, text: str = "") -> bool:
    """Return ``True`` if title or text refers to a non-laptop device or component.

    Checks against ``ProductClassifier.HARD_VETO_PATTERNS``:
    - motherboards (b650, b760, b850, b860, z790, z890, lga1700, am5, etc.)
    - desktop graphics cards (standalone desktop GPUs)
    - desktop towers & prebuilts (desktop pc, aio pc, n50-640, tower)
    - external pc monitors (gaming monitor, ultrawide, vg32, xv27)
    - handheld consoles (nintendo switch, switch 2, legion go, rog ally, steam deck)
    - psus and standalone pc cases

    Applies exceptions: internal screens or mobile GPUs are allowed if accompanied
    by laptop terms (laptop, notebook, chassis, etc.).
    """
    sample = f"{title or ''} {(text or '')[:300]}".strip()
    if not sample:
        return False

    has_laptop_context = bool(_LAPTOP_CONTEXT_PATTERN.search(sample))

    for cat, pat in ProductClassifier.HARD_VETO_PATTERNS:
        if not pat.search(sample):
            continue
        # Exception: allow an internal display or mobile GPU only when the text
        # uses laptop form-factor wording and does not explicitly name an
        # external monitor. Brand sub-brands alone are not enough.
        if cat == "monitor":
            if has_laptop_context and not _EXPLICIT_EXTERNAL_MONITOR_PATTERN.search(sample):
                continue
            return True
        if cat == "gpu":
            if has_laptop_context:
                continue
            return True
        return True

    # The shared classifier patterns only recognize GPUs by "graphics card"
    # wording and only a few monitor model families, so cover the review-title
    # variants used by tech publications as well.
    if _STANDALONE_GPU_PATTERN.search(sample) and not has_laptop_context:
        return True
    if _MONITOR_MODEL_PATTERN.search(sample) and not has_laptop_context:
        return True

    return False


def code_tokens(values: list[str] | tuple[str, ...]) -> set[str]:
    """Extract alphanumeric model codes (letter + digit pairs) from values."""
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue
        for raw in _CODE_TOKEN_RE.findall(str(value)):
            token = raw.upper().strip("-")
            if len(token) < 4:
                continue
            if not (any(char.isdigit() for char in token) and any(char.isalpha() for char in token)):
                continue
            tokens.add(token)
            if "-" in token:
                for part in token.split("-"):
                    part = part.strip()
                    if len(part) >= 4 and any(char.isdigit() for char in part) and any(char.isalpha() for char in part):
                        tokens.add(part)
    return tokens


__all__ = [
    "MIN_DISCUSSION_LENGTH",
    "NEGATIVE_PATTERNS",
    "code_tokens",
    "is_deal_listing",
    "is_non_laptop_device",
    "is_substantive",
]
