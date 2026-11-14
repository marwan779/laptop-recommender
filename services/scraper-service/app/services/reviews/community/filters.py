"""Pure relevance filters shared by community platform scrapers.

Extracted so forum scrapers apply the same deal-listing rule without copying
the pattern table (Single Responsibility, Open/Closed). No I/O.
"""

from __future__ import annotations

import re

from app.domain.reviews.relevance import (
    extract_code_tokens,
    is_non_laptop_device_text,
)

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


def is_deal_listing(text: str) -> bool:
    """Return ``True`` when the text looks like a deal/sale listing."""
    haystack = (text or "").lower()
    return any(pattern.search(haystack) for pattern in NEGATIVE_PATTERNS)


def is_substantive(text: str, min_length: int = MIN_DISCUSSION_LENGTH) -> bool:
    """Return ``True`` when a post body carries enough content to matter."""
    return len((text or "").strip()) >= min_length


def is_non_laptop_device(title: str, text: str = "") -> bool:
    """Delegate non-laptop device and standalone accessory vetoing to domain logic."""
    return is_non_laptop_device_text(title, text)


def code_tokens(values: list[str] | tuple[str, ...]) -> set[str]:
    """Delegate alphanumeric model/SKU extraction to domain logic."""
    return extract_code_tokens(values)


__all__ = [
    "MIN_DISCUSSION_LENGTH",
    "NEGATIVE_PATTERNS",
    "code_tokens",
    "is_deal_listing",
    "is_non_laptop_device",
    "is_substantive",
]
