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

# Lenovo 4-char Machine Type prefix inside 10-char MTM part numbers (e.g. 83DV01HSED -> 83DV, 21NSS29Y00 -> 21NS)
_LENOVO_MTM_RE = re.compile(r"\b((?:8[0-4]|2[0-1])[A-Z0-9]{2})[A-Z0-9]{6}\b")

# ASUS model codes: FA608PM, X1605VA, GX651AX, UX3407QA, G614PH, GU606AR
_ASUS_CODE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,4}[A-Z]{0,3})\b")

# HP consumer chassis series prefix: 15-fa2352TX -> 15-FA, 16-r1011nia -> 16-R
_HP_DASH_CODE_RE = re.compile(r"\b(\d{2}-[a-z]{1,2})\d{3,4}[a-z]{0,3}\b", re.IGNORECASE)

# Dashless HP regional SKUs (e.g. 15FA1043NE -> 15-FA)
_HP_COMPACT_CODE_RE = re.compile(r"\b(\d{2})([a-z]{1,2})\d{4}[a-z]{1,3}\b", re.IGNORECASE)

# Acer / MSI alphanumeric chassis: ANV15-52, PH16-73, B14WGK, A2XWIG, C2HMG
_ALNUM_CHASSIS_RE = re.compile(r"\b([A-Z]{1,3}\d{2,3}[A-Z]{0,2}(?:-\d{2,3})?)\b")

# Single-digit generation alphanumeric chassis codes (e.g. MSI A1MG, C2HMG, C2WE, A2RVE)
_SINGLE_DIGIT_CHASSIS_RE = re.compile(r"\b([A-Z]\d[A-Z]{2,5})\b")

# Screen size integers that distinguish physical chassis within a family
_SCREEN_SIZE_TOKEN_RE = re.compile(r"\b(1[3-8])\b")

# Fallback model differentiators when no alphanumeric chassis code is present
_FALLBACK_MODIFIER_RE = re.compile(r"\b(2-in-1|gaming(?:\s+\d+)?|scar|pro|slim|studio)\b", re.IGNORECASE)

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

# Family tokens that describe marketing/variant flavour rather than the chassis.
_FAMILY_NOISE: frozenset[str] = frozenset({"gaming", "laptop", "notebook", "ai", "hx", "edition", "series", "new"})

# Family names that are too generic to identify a chassis on their own.
_GENERIC_FAMILIES: frozenset[str] = frozenset(
    {"hp", "asus", "lenovo", "dell", "acer", "msi", "gigabyte", "generic", "laptop", "unknown"}
)

# Canonical laptop family inference patterns (ordered most-specific first) used
# when ``laptop_family`` is missing, generic (e.g. "HP", "Notebook"), or polluted
# with CPU specs, screen sizes, or MPN strings.
_KNOWN_FAMILY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\brog\s+strix\s+scar\b", re.IGNORECASE), "rog-strix-scar"),
    (re.compile(r"\brog\s+strix\b", re.IGNORECASE), "rog-strix"),
    (re.compile(r"\brog\s+zephyrus\b", re.IGNORECASE), "rog-zephyrus"),
    (re.compile(r"\brog\s+flow\b", re.IGNORECASE), "rog-flow"),
    (re.compile(r"\bpredator\s+helios\s+neo\b", re.IGNORECASE), "predator-helios-neo"),
    (re.compile(r"\bpredator\s+helios\b", re.IGNORECASE), "predator-helios"),
    (re.compile(r"\bpredator\s+triton\b", re.IGNORECASE), "predator-triton"),
    (re.compile(r"\bloq\s+essential\b", re.IGNORECASE), "loq-essential"),
    (re.compile(r"\blegion\s+pro\b", re.IGNORECASE), "legion-pro"),
    (re.compile(r"\bideapad\s+slim\b", re.IGNORECASE), "ideapad-slim"),
    (re.compile(r"\bzenbook\s+duo\b", re.IGNORECASE), "zenbook-duo"),
    (re.compile(r"\bvivobook\s+go\b", re.IGNORECASE), "vivobook-go"),
    (re.compile(r"\bvivobook\s+pro\b", re.IGNORECASE), "vivobook-pro"),
    (re.compile(r"\baspire\s+go\b", re.IGNORECASE), "aspire-go"),
    (re.compile(r"\bnitro\s+v\b", re.IGNORECASE), "nitro-v"),
    (re.compile(r"\benvy\s+x360\b", re.IGNORECASE), "envy-x360"),
    (re.compile(r"\bhp\s+essential\b", re.IGNORECASE), "hp-essential"),
    (re.compile(r"\bdell\s+pro\b", re.IGNORECASE), "dell-pro"),
    (re.compile(r"\bomnibook\b", re.IGNORECASE), "omnibook"),
    (re.compile(r"\bvivobook\b", re.IGNORECASE), "vivobook"),
    (re.compile(r"\bzenbook\b", re.IGNORECASE), "zenbook"),
    (re.compile(r"\bproart\b", re.IGNORECASE), "proart"),
    (re.compile(r"\bexpertbook\b", re.IGNORECASE), "expertbook"),
    (re.compile(r"\btuf\b", re.IGNORECASE), "tuf"),
    (re.compile(r"\brog\b", re.IGNORECASE), "rog"),
    (re.compile(r"\bloq\b", re.IGNORECASE), "loq"),
    (re.compile(r"\blegion\b", re.IGNORECASE), "legion"),
    (re.compile(r"\bideapad\b", re.IGNORECASE), "ideapad"),
    (re.compile(r"\bthinkpad\b", re.IGNORECASE), "thinkpad"),
    (re.compile(r"\bthinkbook\b", re.IGNORECASE), "thinkbook"),
    (re.compile(r"\byoga\b", re.IGNORECASE), "yoga"),
    (re.compile(r"\bflex\b", re.IGNORECASE), "flex"),
    (re.compile(r"\bvictus\b", re.IGNORECASE), "victus"),
    (re.compile(r"\bomen\b", re.IGNORECASE), "omen"),
    (re.compile(r"\bpavilion\b", re.IGNORECASE), "pavilion"),
    (re.compile(r"\benvy\b", re.IGNORECASE), "envy"),
    (re.compile(r"\bspectre\b", re.IGNORECASE), "spectre"),
    (re.compile(r"\belitebook\b", re.IGNORECASE), "elitebook"),
    (re.compile(r"\bprobook\b", re.IGNORECASE), "probook"),
    (re.compile(r"\bzbook\b", re.IGNORECASE), "zbook"),
    (re.compile(r"\bnitro\b", re.IGNORECASE), "nitro"),
    (re.compile(r"\baspire\b", re.IGNORECASE), "aspire"),
    (re.compile(r"\bswift\b", re.IGNORECASE), "swift"),
    (re.compile(r"\btravelmate\b", re.IGNORECASE), "travelmate"),
    (re.compile(r"\bpredator\b", re.IGNORECASE), "predator"),
    (re.compile(r"\balienware\b", re.IGNORECASE), "alienware"),
    (re.compile(r"\bxps\b", re.IGNORECASE), "xps"),
    (re.compile(r"\blatitude\b", re.IGNORECASE), "latitude"),
    (re.compile(r"\binspiron\b", re.IGNORECASE), "inspiron"),
    (re.compile(r"\bvostro\b", re.IGNORECASE), "vostro"),
    (re.compile(r"\bprecision\b", re.IGNORECASE), "precision"),
    (re.compile(r"\bkatana\b", re.IGNORECASE), "katana"),
    (re.compile(r"\bcyborg\b", re.IGNORECASE), "cyborg"),
    (re.compile(r"\braider\b", re.IGNORECASE), "raider"),
    (re.compile(r"\bvector\b", re.IGNORECASE), "vector"),
    (re.compile(r"\bstealth\b", re.IGNORECASE), "stealth"),
    (re.compile(r"\bprestige\b", re.IGNORECASE), "prestige"),
    (re.compile(r"\bmodern\b", re.IGNORECASE), "modern"),
    (re.compile(r"\bthin\b", re.IGNORECASE), "thin"),
    (re.compile(r"\btitan\b", re.IGNORECASE), "titan"),
    (re.compile(r"\bcrosshair\b", re.IGNORECASE), "crosshair"),
    (re.compile(r"\bmacbook\b", re.IGNORECASE), "macbook"),
    (re.compile(r"\baorus\b", re.IGNORECASE), "aorus"),
    (re.compile(r"\baero\b", re.IGNORECASE), "aero"),
    (re.compile(r"\bhp\s*(250|255r?)\b", re.IGNORECASE), ""),
)

_POLLUTED_FAMILY_RE = re.compile(
    r"(?:ultra-\d|nx-|^[afgsx]?1[1-8]$|-(?:11|12|13|14|15|16|17|18)(?:-|$)|\d{2}[a-z]{3}\d|\d{2}-[a-z]{1,3}\d)",
    re.IGNORECASE,
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
        from ``laptop_model``, ``title``, ``canonical_id``, or brand-specific MPN
        prefixes. When no code can be found, physical differentiators (distinct
        model tier tokens or screen-size class) keep unrelated chassis separated
        before falling back to ``brand:family``.
        """
        brand = cls._normalize(laptop.brand) or "generic"
        family = cls._resolve_family(laptop)
        sub_model = cls.extract_sub_model(laptop)

        if sub_model:
            return f"{brand}:{family}:{sub_model}"

        fallback = cls._fallback_differentiator(laptop)
        if fallback:
            return f"{brand}:{family}:{fallback}"
        return f"{brand}:{family}"

    @classmethod
    def extract_sub_model(cls, laptop: LaptopInputDto) -> str | None:
        """Extract the chassis/sub-model code, or ``None`` when unavailable."""
        brand_lower = (laptop.brand or "").strip().lower()
        for source in (laptop.laptop_model, laptop.title, laptop.canonical_id):
            code = cls._code_from_text(source, brand_lower=brand_lower)
            if code:
                return code

        if brand_lower == "hp" and laptop.mpn:
            hp_compact = _HP_COMPACT_CODE_RE.search(str(laptop.mpn).strip())
            if hp_compact:
                return f"{hp_compact.group(1)}-{hp_compact.group(2).upper()}"

        if brand_lower == "lenovo":
            for source in (laptop.laptop_model, laptop.title, laptop.mpn):
                if not source:
                    continue
                mtm = _LENOVO_MTM_RE.search(str(source).upper())
                if mtm:
                    return mtm.group(1)
        return None

    @classmethod
    def _code_from_text(cls, text: str | None, *, brand_lower: str = "") -> str | None:
        if not text:
            return None
        cleaned = _WHITESPACE_RE.sub(" ", str(text).replace("_", " ")).strip()
        if not cleaned:
            return None

        lenovo_match = _LENOVO_CHASSIS_RE.search(cleaned)
        if lenovo_match:
            return lenovo_match.group(1).upper()

        hp_dash = _HP_DASH_CODE_RE.search(cleaned)
        if hp_dash:
            return hp_dash.group(1).upper()

        if brand_lower == "hp":
            hp_compact = _HP_COMPACT_CODE_RE.search(cleaned)
            if hp_compact:
                return f"{hp_compact.group(1)}-{hp_compact.group(2).upper()}"

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

        if brand_lower != "hp":
            for match in _SINGLE_DIGIT_CHASSIS_RE.finditer(cleaned.upper()):
                candidate = match.group(1)
                if cls._is_component(candidate):
                    continue
                return candidate

        return None

    @classmethod
    def _fallback_differentiator(cls, laptop: LaptopInputDto) -> str | None:
        """Preserve physical tier or screen size when no chassis code exists."""
        tokens: list[str] = []
        model_text = _WHITESPACE_RE.sub(" ", str(laptop.laptop_model or "")).strip()
        if model_text:
            modifier = _FALLBACK_MODIFIER_RE.search(model_text)
            if modifier:
                norm_mod = cls._normalize(modifier.group(1))
                if norm_mod and norm_mod not in (cls._normalize(laptop.laptop_family) or ""):
                    tokens.append(norm_mod)

            size_match = _SCREEN_SIZE_TOKEN_RE.search(model_text)
            if size_match:
                tokens.append(size_match.group(1))

        if laptop.screen_size is not None and not any(t.isdigit() and len(t) == 2 for t in tokens):
            size_int = int(laptop.screen_size)
            if 11 <= size_int <= 18:
                tokens.append(str(size_int))

        return "-".join(tokens) if tokens else None

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
    def _resolve_family(cls, laptop: LaptopInputDto) -> str:
        """Resolve canonical chassis family, inferring from model/title when DB metadata is generic or noisy."""
        normalized = cls._normalize_family(laptop.laptop_family)
        if normalized and not _POLLUTED_FAMILY_RE.search(normalized):
            return normalized

        inferred = cls._infer_known_family(laptop.laptop_model, laptop.title, laptop.laptop_family)
        if inferred:
            return inferred
        return normalized or "unknown"

    @classmethod
    def _infer_known_family(cls, *sources: str | None) -> str | None:
        for source in sources:
            if not source:
                continue
            text = _WHITESPACE_RE.sub(" ", str(source)).strip()
            for pattern, slug in _KNOWN_FAMILY_PATTERNS:
                match = pattern.search(text)
                if match:
                    return slug or match.group(1).lower()
        return None

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
