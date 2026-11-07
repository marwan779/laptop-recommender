"""Pure domain query generation for YouTube review discovery.

Contains no network, filesystem, or database dependencies. Given a review target
it deterministically produces the ordered search queries the collector should
try, which makes query strategy unit-testable in milliseconds.
"""

from __future__ import annotations

import re

from app.schemas.events import LaptopReviewTarget

_WHITESPACE_RE = re.compile(r"\s+")


class YouTubeQueryBuilder:
    """Build prioritized English and Arabic YouTube search queries for a target.

    Query strategy:
        1. Primary (English): ``"{brand} {family} {clean_model} review"``
        2. Secondary (Arabic): ``"مراجعة {brand} {family} {clean_model}"``
    """

    def build_queries(self, target: LaptopReviewTarget) -> list[str]:
        """Return the ordered list of search queries for one target.

        Always returns a list whose first element is a usable query, even when
        identity fields are sparse.
        """
        brand = self._clean(target.brand)
        family = self._clean(target.laptop_family)
        model = self._clean_model(target.laptop_model, family, brand)

        subject = self._join_subject(brand, family, model)
        if not subject:
            # Ultimate fallback: the canonical slug is still a searchable phrase.
            subject = self._clean(target.canonical_id) or self._clean(target.laptop_id) or "laptop"

        primary = self._squash(f"{subject} review")
        secondary = self._squash(f"مراجعة {subject}")
        return [primary, secondary]

    @staticmethod
    def _clean(value: str | None) -> str:
        """Trim and collapse internal whitespace."""
        if not value:
            return ""
        return _WHITESPACE_RE.sub(" ", str(value)).strip()

    def _clean_model(self, model: str | None, family: str, brand: str = "") -> str:
        """Remove repeated brand/family prefixes from the model.

        Guarantees a query like ``"LOQ LOQ 15IRX9"`` or
        ``"HP Victus HP Victus 15-fa2352TX"`` is never produced.
        """
        cleaned = self._clean(model)
        if not cleaned:
            return cleaned

        identity_tokens = {token for token in f"{brand} {family}".lower().split() if token}

        changed = True
        while changed and cleaned:
            changed = False
            lowered = cleaned.lower()
            for prefix in (family, brand):
                if prefix and lowered.startswith(prefix.lower()):
                    remainder = cleaned[len(prefix) :].lstrip(" -–—:")
                    if remainder:
                        cleaned = remainder
                        changed = True
                        break
            if changed:
                continue
            parts = cleaned.split()
            if parts and parts[0].lower() in identity_tokens:
                cleaned = " ".join(parts[1:])
                changed = True

        return cleaned

    def _join_subject(self, brand: str, family: str, model: str) -> str:
        """Join identity parts without duplicating tokens."""
        parts: list[str] = []
        seen: set[str] = set()

        for part in (brand, family, model):
            if not part:
                continue
            key = part.lower()
            if key in seen:
                continue
            # Skip a part that is entirely contained in the previous one
            # (e.g. family "LOQ" already inside model "LOQ 15IRX9").
            if parts and key in parts[-1].lower():
                continue
            seen.add(key)
            parts.append(part)

        return self._squash(" ".join(parts))

    @staticmethod
    def _squash(text: str) -> str:
        return _WHITESPACE_RE.sub(" ", text).strip()


__all__ = ["YouTubeQueryBuilder"]
