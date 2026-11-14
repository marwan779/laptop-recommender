"""Pure domain query generation for YouTube review discovery.

Contains no network, filesystem, or database dependencies. Given a review target
it deterministically produces the ordered search queries the collector should
try, which makes query strategy unit-testable in milliseconds.
"""

from __future__ import annotations

import re

from app.domain.reviews.relevance import extract_code_tokens
from app.domain.reviews.subject import build_subject
from app.schemas.events import LaptopReviewTarget

_WHITESPACE_RE = re.compile(r"\s+")
_HAS_SIZE_RE = re.compile(r"\b1[1-8]\b")
_ARABIC_LAPTOP = "لابتوب"


class YouTubeQueryBuilder:
    """Build prioritized English and Arabic YouTube search queries for a target.

    Query strategy:
        1. Primary (English): ``"{brand} {family} {clean_model} review"``
        2. Secondary (Arabic): ``"مراجعة {brand} {family} {clean_model}"``
    """

    def build_queries(self, target: LaptopReviewTarget) -> list[str]:
        """Return the ordered list of search queries for one target.

        Always returns a list whose first element is a usable query, even when
        identity fields are sparse. Disambiguates non-SKU subjects with screen
        size and/or ``laptop`` context so generic queries avoid monitors/GPUs.
        """
        subject = build_subject(target)
        codes = extract_code_tokens([target.laptop_model, subject])

        # Disambiguate sparse/non-SKU targets using screen-size class + "laptop" form factor.
        if not codes:
            if target.screen_size is not None and not _HAS_SIZE_RE.search(subject):
                size_int = int(target.screen_size)
                if 11 <= size_int <= 18:
                    subject = f"{subject} {size_int}"
            en_subject = subject if "laptop" in subject.lower() else f"{subject} laptop"
            ar_subject = subject if _ARABIC_LAPTOP in subject else f"{_ARABIC_LAPTOP} {subject}"
        else:
            en_subject = subject
            ar_subject = subject

        primary = self._squash(f"{en_subject} review")
        secondary = self._squash(f"مراجعة {ar_subject}")
        return [primary, secondary]

    @staticmethod
    def _squash(text: str) -> str:
        return _WHITESPACE_RE.sub(" ", text).strip()


__all__ = ["YouTubeQueryBuilder"]
