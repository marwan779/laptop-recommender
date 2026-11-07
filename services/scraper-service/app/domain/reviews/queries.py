"""Pure domain query generation for YouTube review discovery.

Contains no network, filesystem, or database dependencies. Given a review target
it deterministically produces the ordered search queries the collector should
try, which makes query strategy unit-testable in milliseconds.
"""

from __future__ import annotations

import re

from app.domain.reviews.subject import build_subject
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
        subject = build_subject(target)

        primary = self._squash(f"{subject} review")
        secondary = self._squash(f"مراجعة {subject}")
        return [primary, secondary]

    @staticmethod
    def _squash(text: str) -> str:
        return _WHITESPACE_RE.sub(" ", text).strip()


__all__ = ["YouTubeQueryBuilder"]
