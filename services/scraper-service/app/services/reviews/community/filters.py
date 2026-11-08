"""Pure relevance filters shared by community platform scrapers.

Extracted so forum scrapers apply the same deal-listing rule without copying
the pattern table (Single Responsibility, Open/Closed). No I/O.
"""

from __future__ import annotations

import re

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


def is_deal_listing(text: str) -> bool:
    """Return ``True`` when the text looks like a deal/sale listing."""
    haystack = (text or "").lower()
    return any(pattern.search(haystack) for pattern in NEGATIVE_PATTERNS)


def is_substantive(text: str, min_length: int = MIN_DISCUSSION_LENGTH) -> bool:
    """Return ``True`` when a post body carries enough content to matter."""
    return len((text or "").strip()) >= min_length


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
                    if (
                        len(part) >= 4
                        and any(char.isdigit() for char in part)
                        and any(char.isalpha() for char in part)
                    ):
                        tokens.add(part)
    return tokens


__all__ = [
    "MIN_DISCUSSION_LENGTH",
    "NEGATIVE_PATTERNS",
    "code_tokens",
    "is_deal_listing",
    "is_substantive",
]
