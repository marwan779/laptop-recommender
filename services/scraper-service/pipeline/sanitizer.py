"""Layer 2: Text Sanitizer Layer.

Cleanses raw web strings, table cells, and section text before any regex,
CPU lookup, or deterministic extraction takes place.
"""

from __future__ import annotations

import re
from typing import Any

PLACEHOLDER_WORDS: set[str] = {
    "tbd",
    "n/a",
    "na",
    "-",
    "--",
    "---",
    "estimated",
    "expected",
    "approx",
    "approximate",
    "varies",
    "varies by model",
    "depending on model",
    "none",
    "unknown",
    "null",
    "not specified",
    "not available",
    "optional",
    "default",
    "see details",
}


class TextSanitizer:
    """Production-grade text sanitizer for scraping and extraction."""

    @staticmethod
    def clean_text(s: Any) -> str:
        """Strip invisible marks, trademarks, and footnote clusters."""
        if s is None:
            return ""
        text = str(s)

        # 1. Strip zero-width, bidirectional, and non-breaking unicode
        text = re.sub(r"[\u200e\u200f\u200b\u200c\u200d\uFEFF\xa0]", " ", text)

        # 2. Strip trademark and copyright symbols
        text = re.sub(r"[®™©]", " ", text)

        # 3. Normalize various Unicode dashes to standard ASCII hyphen
        text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", text)

        # 4. Remove parenthesized/bracketed footnote markers e.g. (1), [2], ( 14 )
        text = re.sub(r"[\(\[]\s*\d{1,2}\s*[\)\]]", " ", text)

        # 5. Remove trailing OEM footnote clusters (e.g. " 1 2", " 10 11 12")
        text = re.sub(r"\b(?:\d{1,2}\s+){1,4}\d{1,2}$", "", text.strip())

        # 6. Collapse consecutive whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    def is_placeholder(cls, s: Any) -> bool:
        """Check if a string represents an unpopulated placeholder."""
        if s is None:
            return True
        cleaned = cls.clean_text(s).lower()
        if not cleaned or cleaned in PLACEHOLDER_WORDS:
            return True
        if re.search(
            r"\b(?:estimated|tbd|expected|varies|depending\s+on\s+model|not\s+specified)\b",
            cleaned,
        ):
            return True
        return False

    @classmethod
    def sanitize_value(cls, val: Any) -> str | None:
        """Clean a spec value string, returning None if placeholder or empty."""
        cleaned = cls.clean_text(val)
        if cls.is_placeholder(cleaned):
            return None
        return cleaned

    @classmethod
    def sanitize_table(cls, table: dict[str, str]) -> dict[str, str]:
        """Clean all keys and values in a table row mapping."""
        sanitized = {}
        for k, v in table.items():
            clean_k = cls.clean_text(k)
            clean_v = cls.sanitize_value(v)
            if clean_k and clean_v:
                sanitized[clean_k] = clean_v
        return sanitized

    @classmethod
    def sanitize_sections(cls, sections: dict[str, str]) -> dict[str, str]:
        """Clean section-level text blocks."""
        sanitized = {}
        for sec_name, text in sections.items():
            clean_sec = cls.clean_text(sec_name)
            lines = [cls.clean_text(line) for line in text.splitlines()]
            # Filter empty or placeholder lines
            filtered_lines = [l for l in lines if l and not cls.is_placeholder(l)]
            if filtered_lines:
                sanitized[clean_sec] = "\n".join(filtered_lines)
        return sanitized
