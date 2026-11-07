"""Pure domain query generation for community (Reddit, forums) review discovery.

Produces *aspect-oriented* Boolean queries instead of a single generic query, so
each platform search surfaces discussion of a specific hardware concern:
thermals, build quality, fan noise/battery, and a general review sweep.

Zero network or database dependencies — unit-testable in milliseconds.
"""

from __future__ import annotations

import re

from app.domain.reviews.subject import build_subject
from app.schemas.events import LaptopReviewTarget

_WHITESPACE_RE = re.compile(r"\s+")

# Aspect query templates. ``{subject}`` is replaced with the cleaned identity.
ASPECT_QUERY_TEMPLATES: tuple[str, ...] = (
    "{subject} (thermals OR cooling OR overheating OR temperatures)",
    "{subject} (hinge OR build quality OR flex OR durability)",
    "{subject} (fan noise OR loud fans OR battery life OR battery drain)",
    "{subject} review",
)


class CommunityQueryBuilder:
    """Build aspect-oriented Boolean search queries for community platforms.

    Example output for ``Lenovo LOQ 15IRX9``::

        [
            "Lenovo LOQ 15IRX9 (thermals OR cooling OR overheating OR temperatures)",
            "Lenovo LOQ 15IRX9 (hinge OR build quality OR flex OR durability)",
            "Lenovo LOQ 15IRX9 (fan noise OR loud fans OR battery life OR battery drain)",
            "Lenovo LOQ 15IRX9 review",
        ]
    """

    def build_queries(self, target: LaptopReviewTarget) -> list[str]:
        """Return the four aspect queries for one target, in priority order."""
        subject = build_subject(target)
        return [self._squash(template.format(subject=subject)) for template in ASPECT_QUERY_TEMPLATES]

    @staticmethod
    def _squash(text: str) -> str:
        return _WHITESPACE_RE.sub(" ", text).strip()


__all__ = ["ASPECT_QUERY_TEMPLATES", "CommunityQueryBuilder"]
