"""Pure domain query generation for community (Reddit, forums) review discovery.

Two strategies coexist here:

* ``build_queries`` produces *aspect-oriented* Boolean queries used by Reddit
  (thermals, build quality, fan noise/battery, general review).
* ``build_platform_queries`` produces the tailored, platform-specific queries
  used by editorial and regional community sources. Each platform gets the
  query shape that matches its search engine instead of one generic subject.

Zero network or database dependencies — unit-testable in milliseconds.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.domain.reviews.subject import build_subject, clean_text
from app.schemas.events import LaptopReviewTarget

_WHITESPACE_RE = re.compile(r"\s+")

# Aspect query templates. ``{subject}`` is replaced with the cleaned identity.
ASPECT_QUERY_TEMPLATES: tuple[str, ...] = (
    "{subject} (thermals OR cooling OR overheating OR temperatures)",
    "{subject} (hinge OR build quality OR flex OR durability)",
    "{subject} (fan noise OR loud fans OR battery life OR battery drain)",
    "{subject} review",
)

# Chassis/sub-model code patterns, ordered most specific first. Mirrors the
# catalog-service chassis extractor so both services agree on identity codes.
_LENOVO_CHASSIS_RE = re.compile(r"\b(\d{2}[A-Z]{3}\d{1,2}[A-Z]?)\b")
_HP_DASH_CODE_RE = re.compile(r"\b(\d{2}-[A-Z]{1,3}\d{3,4}[A-Z]{0,3})\b", re.IGNORECASE)
_DASHED_CHASSIS_RE = re.compile(r"\b([A-Z]{2,4}\d{2,4}-[A-Z0-9]{2,6})\b")
_ASUS_CODE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,4}[A-Z]{0,3})\b")

# Tokens that are hardware components or OS markers, not chassis identifiers.
_COMPONENT_TOKENS: frozenset[str] = frozenset(
    {
        "RTX",
        "GTX",
        "RAM",
        "SSD",
        "HDD",
        "NVME",
        "PCIE",
        "DDR",
        "DDR4",
        "DDR5",
        "LPDDR",
        "LPDDR5",
        "LPDDR5X",
        "WIFI",
        "HDMI",
        "USB",
        "OLED",
        "IPS",
        "FHD",
        "QHD",
        "WQXGA",
        "WUXGA",
        "GB",
        "TB",
        "MHZ",
        "HZ",
        "INTEL",
        "AMD",
        "NVIDIA",
        "RYZEN",
        "CORE",
        "ULTRA",
        "TOPS",
        "WINDOWS",
        "WIN",
        "CPU",
        "GPU",
        "NPU",
    }
)


@dataclass(frozen=True, slots=True)
class CommunityQuerySet:
    """The tailored query for each community platform family."""

    editorial: str
    forum: str
    regional: str


def screen_size_token(target: LaptopReviewTarget) -> str:
    """Return the whole-inch screen size token, or an empty string.

    Uses integer floor truncation so standard panels match their marketing tier
    (e.g. 15.6" -> "15" for "LOQ 15" / "Victus 15", and 17.3" -> "17").
    """
    if target.screen_size is None:
        return ""
    return str(int(target.screen_size))


def clean_sub_model(target: LaptopReviewTarget) -> str:
    """Extract the chassis/sub-model code from a target, or ``""``.

    Example: ``Lenovo LOQ 15IRX9`` -> ``"15IRX9"``.
    """
    for source in (target.laptop_model, target.title, target.canonical_id, *target.skus):
        code = _code_from_text(source)
        if code:
            return code
    return ""


def _code_from_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", str(value)).strip()
    if not cleaned:
        return None

    for pattern in (_LENOVO_CHASSIS_RE, _HP_DASH_CODE_RE):
        match = pattern.search(cleaned)
        if match:
            return match.group(1).upper()

    upper = cleaned.upper()
    dashed = _DASHED_CHASSIS_RE.search(upper)
    if dashed and not _is_component(dashed.group(1)):
        return dashed.group(1)

    for match in _ASUS_CODE_RE.finditer(upper):
        candidate = match.group(1)
        if _is_component(candidate):
            continue
        if any(char.isdigit() for char in candidate):
            return candidate
    return None


def _is_component(token: str) -> bool:
    head = re.split(r"[-_]", token.upper(), maxsplit=1)[0]
    return head in _COMPONENT_TOKENS


class CommunityQueryBuilder:
    """Build aspect-oriented and platform-tailored community search queries.

    Example output for a ``Lenovo LOQ 15IRX9`` target at 15.6 inches::

        CommunityQuerySet(
            editorial="Lenovo LOQ 15 review",
            forum="Lenovo 15IRX9",
            regional="LOQ 15IRX9",
        )
    """

    def build_queries(self, target: LaptopReviewTarget) -> list[str]:
        """Return the four aspect queries for one target, in priority order."""
        subject = build_subject(target)
        return [self._squash(template.format(subject=subject)) for template in ASPECT_QUERY_TEMPLATES]

    def editorial_query(self, target: LaptopReviewTarget) -> str:
        """Editorial review-portal query, e.g. ``"Lenovo LOQ 15 review"``."""
        brand = clean_text(target.brand)
        family = clean_text(target.laptop_family)
        parts = [brand, family, screen_size_token(target), "review"]
        return self._squash(" ".join(part for part in parts if part))

    def forum_query(self, target: LaptopReviewTarget) -> str:
        """Hardware-forum query, e.g. ``"Lenovo 15IRX9"``.

        Falls back to brand + family + screen size when no chassis code exists.
        """
        brand = clean_text(target.brand)
        sub_model = clean_sub_model(target)
        if sub_model:
            return self._squash(f"{brand} {sub_model}")

        family = clean_text(target.laptop_family)
        parts = [brand, family, screen_size_token(target)]
        query = self._squash(" ".join(part for part in parts if part))
        return query or clean_text(target.canonical_id)

    def regional_query(self, target: LaptopReviewTarget) -> str:
        """Regional/Arabic community query, e.g. ``"LOQ 15IRX9"``."""
        family = clean_text(target.laptop_family)
        anchor = clean_sub_model(target) or screen_size_token(target)
        query = self._squash(f"{family} {anchor}")
        return query or clean_text(target.canonical_id)

    def build_platform_queries(self, target: LaptopReviewTarget) -> CommunityQuerySet:
        """Return every tailored query for one target."""
        return CommunityQuerySet(
            editorial=self.editorial_query(target),
            forum=self.forum_query(target),
            regional=self.regional_query(target),
        )

    @staticmethod
    def _squash(text: str) -> str:
        return _WHITESPACE_RE.sub(" ", text).strip()


__all__ = [
    "ASPECT_QUERY_TEMPLATES",
    "CommunityQueryBuilder",
    "CommunityQuerySet",
    "clean_sub_model",
    "screen_size_token",
]
