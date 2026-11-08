"""Pure domain chassis resolution for community review scraping.

This module is intentionally dependency-free: it imports only the Python
standard library. It must never import SQLAlchemy, asyncpg, FastAPI, httpx, or
any other infrastructure/framework package so it stays unit-testable in
milliseconds without a database.

Responsibility: collapse many concrete laptop SKU rows into one review target
per physical chassis. For example two Lenovo LOQ 15IRX9 variants that differ
only in RAM/storage collapse into a single chassis target carrying every
variant's MPN.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import re

# ─── Domain DTOs ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LaptopInputDto:
    """Pure input projection of one laptop configuration row.

    Decouples chassis resolution from SQLAlchemy ORM entities: the application
    layer builds these DTOs from ``LaptopConfiguration`` instances.
    """

    laptop_id: str
    canonical_id: str
    title: str | None = None
    brand: str | None = None
    laptop_family: str | None = None
    laptop_model: str | None = None
    mpn: str | None = None
    thumbnail_url: str | None = None
    screen_size: float | None = None
    retailer_skus: tuple[str, ...] = ()
    product_urls: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedReviewTarget:
    """Pure resolved review target for one physical chassis.

    Mirrors the transport-level ``LaptopReviewTarget`` schema but deliberately
    omits ``search_queries``: query generation belongs solely to the scraper
    service. ``chassis_key`` and ``variant_count`` are domain-only
    observability facts used for logging and tests.
    """

    laptop_id: str
    canonical_id: str
    chassis_key: str
    variant_count: int
    title: str | None = None
    brand: str | None = None
    laptop_family: str | None = None
    laptop_model: str | None = None
    mpn: str | None = None
    manufacturer_part_number: str | None = None
    retailer_sku: str | None = None
    skus: tuple[str, ...] = ()
    mpns: tuple[str, ...] = ()
    product_urls: tuple[str, ...] = ()
    thumbnail_url: str | None = None
    screen_size: float | None = None
    matched_laptop_ids: tuple[str, ...] = ()
    matched_canonical_ids: tuple[str, ...] = ()


# ─── Chassis code extraction ────────────────────────────────────────────────

_WHITESPACE_RE = re.compile(r"\s+")
_SEPARATOR_RE = re.compile(r"\s+[–—|/]\s+|\s+-\s+")

# Lenovo chassis codes: 15IRX9, 15ARP10E, 16IAX10H, 15IRH10, 15IRU8, 15AHP9
_LENOVO_CHASSIS_RE = re.compile(r"\b(\d{2}[A-Z]{3}\d{1,2}[A-Z]?)\b")

# ASUS model codes: FA608PM, X1605VA, GX651AX, UX3407QA, G614PH, GU606AR
_ASUS_CODE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,4}[A-Z]{0,3})\b")

# HP consumer codes: 15-fa2352TX, 16-r1011nia, 15-fd1062ne
_HP_DASH_CODE_RE = re.compile(r"\b(\d{2}-[a-z]{1,3}\d{3,4}[a-z]{0,3})\b", re.IGNORECASE)

# Acer / MSI alphanumeric chassis: ANV15-52, PH16-73, B14WGK, A2XWIG, C2HMG
_ALNUM_CHASSIS_RE = re.compile(r"\b([A-Z]{1,3}\d{2,3}[A-Z]{0,2}(?:-\d{2,3})?)\b")

# Tokens that are hardware components or OS markers, not chassis identifiers.
_COMPONENT_TOKENS: frozenset[str] = frozenset(
    {
        "RTX",
        "GTX",
        "RAM",
        "SSD",
        "HDD",
        "NVME",
        "PCI",
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
        "BT",
        "OS",
        "WIN",
        "WINDOWS",
        "AI",
        "NPU",
        "CPU",
        "GPU",
        "TOUCH",
        "GEN",
        "TH",
        "ST",
        "ND",
        "RD",
    }
)

# Family tokens that describe marketing/variant flavour rather than the family.
_FAMILY_NOISE: frozenset[str] = frozenset(
    {"gaming", "laptop", "notebook", "ai", "hx", "essential", "edition", "series", "new"}
)

# Family names that are too generic to identify a chassis on their own.
_GENERIC_FAMILIES: frozenset[str] = frozenset(
    {"hp", "asus", "lenovo", "dell", "acer", "msi", "gigabyte", "generic", "laptop", "unknown"}
)


class ChassisKeyExtractor:
    """Derive a stable chassis identity key from laptop identity fields.

    The extractor is deterministic and brand-aware: it prefers an explicit
    model/part code (``15IRX9``, ``FA608PM``, ``X1605VA``) and falls back to a
    normalized ``brand:family`` pair, then to a normalized title fragment.
    """

    @classmethod
    def extract(cls, laptop: LaptopInputDto) -> str:
        """Return the normalized chassis key for one laptop row.

        Key shape is ``brand:family:sub_model``. The sub-model code is extracted
        from ``laptop_model``, ``title``, or ``canonical_id`` via regex. When no
        code can be found, the normalized ``brand:family`` pair is used so the
        laptop still lands in a stable group.
        """
        brand = cls._normalize(laptop.brand) or "generic"
        family = cls._normalize_family(laptop.laptop_family) or "unknown"
        sub_model = cls.extract_sub_model(laptop)

        if sub_model:
            return f"{brand}:{family}:{sub_model}"
        return f"{brand}:{family}"

    @classmethod
    def extract_sub_model(cls, laptop: LaptopInputDto) -> str | None:
        """Extract the chassis/sub-model code, or ``None`` when unavailable."""
        for source in (laptop.laptop_model, laptop.title, laptop.canonical_id):
            code = cls._code_from_text(source)
            if code:
                return code
        return None

    @classmethod
    def _code_from_text(cls, text: str | None) -> str | None:
        if not text:
            return None
        cleaned = _WHITESPACE_RE.sub(" ", str(text)).strip()
        if not cleaned:
            return None

        for pattern in (_LENOVO_CHASSIS_RE, _HP_DASH_CODE_RE):
            match = pattern.search(cleaned)
            if match:
                return match.group(1).upper()

        # Prefer a dashed alphanumeric chassis (ANV15-52, PH16-73) over its head.
        dashed = re.search(r"\b([A-Z]{2,4}\d{2,4}-[A-Z0-9]{2,6})\b", cleaned.upper())
        if dashed and not cls._is_component(dashed.group(1)):
            return dashed.group(1)

        for pattern in (_ASUS_CODE_RE, _ALNUM_CHASSIS_RE):
            for match in pattern.finditer(cleaned.upper()):
                candidate = match.group(1)
                if cls._is_component(candidate):
                    continue
                if not any(char.isdigit() for char in candidate):
                    continue
                return candidate
        return None

    @classmethod
    def _is_component(cls, token: str) -> bool:
        head = re.split(r"[-_]", token.upper(), maxsplit=1)[0]
        return head in _COMPONENT_TOKENS

    @staticmethod
    def _normalize(value: str | None) -> str | None:
        if not value:
            return None
        text = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
        return text or None

    @classmethod
    def _normalize_family(cls, value: str | None) -> str | None:
        """Normalize a family name, dropping marketing noise and generic names."""
        normalized = cls._normalize(value)
        if not normalized:
            return None
        tokens = [token for token in normalized.split("-") if token and token not in _FAMILY_NOISE]
        if not tokens:
            return None
        candidate = "-".join(tokens)
        if candidate in _GENERIC_FAMILIES:
            return None
        return candidate


# ─── Aggregation ────────────────────────────────────────────────────────────


class ChassisTargetResolver:
    """Collapse laptop variants into one review target per chassis.

    Pure, stateless, and side-effect free. The resolver never mutates its
    inputs and never performs I/O.
    """

    def __init__(self, extractor: type[ChassisKeyExtractor] = ChassisKeyExtractor) -> None:
        self.extractor = extractor

    def resolve(self, laptops: Sequence[LaptopInputDto] | Iterable[LaptopInputDto]) -> list[ResolvedReviewTarget]:
        """Group laptops by chassis and return one aggregated target per group."""
        groups: dict[str, list[LaptopInputDto]] = {}
        for laptop in laptops or ():
            key = self.extractor.extract(laptop)
            groups.setdefault(key, []).append(laptop)

        return [self._build_target(key, members) for key, members in groups.items()]

    def _build_target(self, chassis_key: str, members: list[LaptopInputDto]) -> ResolvedReviewTarget:
        representative = members[0]

        mpns: list[str] = []
        skus: list[str] = []
        product_urls: list[str] = []

        for member in members:
            self._append_unique(mpns, member.mpn)
            for sku in member.retailer_skus:
                self._append_unique(skus, sku)
            for url in member.product_urls:
                self._append_unique(product_urls, url)

        primary_mpn = representative.mpn or (mpns[0] if mpns else None)

        return ResolvedReviewTarget(
            laptop_id=representative.laptop_id,
            canonical_id=representative.canonical_id,
            chassis_key=chassis_key,
            variant_count=len(members),
            title=representative.title,
            brand=representative.brand,
            laptop_family=representative.laptop_family,
            laptop_model=representative.laptop_model,
            mpn=primary_mpn,
            manufacturer_part_number=primary_mpn,
            retailer_sku=skus[0] if skus else None,
            skus=tuple(skus),
            mpns=tuple(mpns),
            product_urls=tuple(product_urls),
            thumbnail_url=representative.thumbnail_url,
            screen_size=self._resolve_screen_size(members),
            matched_laptop_ids=tuple(member.laptop_id for member in members),
            matched_canonical_ids=tuple(member.canonical_id for member in members),
        )

    @staticmethod
    def _resolve_screen_size(members: Sequence[LaptopInputDto]) -> float | None:
        """Pick the group's most common non-null screen size.

        Variants of one chassis normally share a screen size; when a bad row
        disagrees, the modal value wins. Ties fall back to the first member
        that reported a size, which keeps resolution deterministic.
        """
        counts: dict[float, int] = {}
        first_seen: dict[float, int] = {}
        for index, member in enumerate(members):
            if member.screen_size is None:
                continue
            counts[member.screen_size] = counts.get(member.screen_size, 0) + 1
            first_seen.setdefault(member.screen_size, index)

        if not counts:
            return None

        return max(counts, key=lambda size: (counts[size], -first_seen[size]))

    @staticmethod
    def _append_unique(target: list[str], value: str | None) -> None:
        if not value:
            return
        cleaned = str(value).strip()
        if cleaned and cleaned not in target:
            target.append(cleaned)


__all__ = [
    "ChassisKeyExtractor",
    "ChassisTargetResolver",
    "LaptopInputDto",
    "ResolvedReviewTarget",
]
