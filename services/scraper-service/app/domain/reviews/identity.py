"""Resolve a stable laptop identity from catalog and event fields.

The extractor deliberately treats explicit database/identity fields as more
trustworthy than text-derived guesses. It reuses the existing pure
``ModelNormalizer`` for chassis/SKU token extraction and adds review-specific
MPN and language handling.
"""

from __future__ import annotations

import hashlib
import re

from app.core.normalizer import ModelNormalizer
from app.domain.reviews.models import ReviewIdentity, ReviewTargetInput
from app.domain.reviews.vocabulary import BRAND_ALIASES, FAMILY_ALIASES, normalize_lookup

_WHITESPACE_RE = re.compile(r"\s+")
_TITLE_SEPARATOR_RE = re.compile(r"\s+[–—|]\s+|\s+-\s+")
_MODEL_CODE_RE = re.compile(r"^[A-Za-z]{1,4}\d{3,5}[A-Za-z0-9]{0,4}(?:-[A-Za-z0-9]{4,8})?$")
_MPN_COMPACT_RE = re.compile(r"^90[A-Z0-9]{6,8}[A-Z0-9]{4,8}$")
_ARABIC_LETTER_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_OR_ARABIC_LETTER_RE = re.compile(r"[A-Za-z\u0600-\u06FF]")
_INTEL_CPU_RE = re.compile(r"\b(i[3579])[-\s]?(\d{4,5}[A-Z]{0,2})\b", re.IGNORECASE)
_AMD_CPU_RE = re.compile(r"\b(ryzen\s+[3579])\s+(\d{4}[A-Z]{0,2})\b", re.IGNORECASE)
_ULTRA_CPU_RE = re.compile(r"\b(ultra\s+[579])\s+(\d{3}[A-Z]{0,2})\b", re.IGNORECASE)
_RAW_NOISE_TERMS: tuple[str, ...] = (
    "includes mouse & bag",
    "includes mouse and bag",
    "free bag",
    "with bag",
    "windows 11",
    "windows 10",
    "special offer",
    "best seller",
    "hot deal",
)


class ReviewIdentityExtractor:
    """Build a ``ReviewIdentity`` from one review target."""

    def extract(self, target: ReviewTargetInput) -> ReviewIdentity:
        title = self._clean_text(target.title)
        title_core = self._build_title_core(title)

        tokens = self._extract_tokens(
            [
                title,
                *target.skus,
                target.retailer_sku or "",
                target.mpn or "",
                target.manufacturer_part_number or "",
                *target.mpns,
            ]
        )

        brand = self._canonical_brand(target.brand) or self._brand_from_text(title) or self._brand_from_text(title_core)
        family = self._canonical_family(target.laptop_family) or self._family_from_text(title)
        if family is None and target.laptop_model:
            family = self._family_from_text(target.laptop_model)

        model = self._clean_text(target.laptop_model) or None
        if not model and family:
            model = self._model_from_text(title, family)

        mpn, mpn_compact = self._resolve_mpn(target, tokens.get("mpn"))
        full_sku = tokens.get("full_sku")
        sub_model = tokens.get("sub_model")
        base_model = tokens.get("base_model")

        sku_candidates = self._collect_sku_candidates(target, tokens)
        mpn_candidates = self._collect_mpn_candidates(target, tokens)

        # The product title is the strongest language signal. Only fall back to
        # identity fields when the caller supplied no title.
        language_source = title or " ".join(part for part in (brand or "", family or "", model or "") if part)
        language_hint = self._language_hint(language_source)

        warnings = self._warnings(
            target=target,
            title=title,
            brand=brand,
            family=family,
            model=model,
            sku_candidates=sku_candidates,
            mpn_candidates=mpn_candidates,
        )
        target_key = self._target_key(
            target=target,
            brand=brand,
            family=family,
            model=model,
            title_core=title_core,
            title=title,
            full_sku=full_sku,
            mpn=mpn,
            sku_candidates=sku_candidates,
        )

        return ReviewIdentity(
            target_key=target_key,
            laptop_id=target.laptop_id,
            canonical_id=target.canonical_id,
            brand=brand,
            family=family,
            model=model,
            title=title,
            title_core=title_core,
            full_sku=full_sku,
            sub_model=sub_model,
            base_model=base_model,
            mpn=mpn,
            mpn_compact=mpn_compact,
            sku_candidates=sku_candidates,
            mpn_candidates=mpn_candidates,
            cpu_hint=self._extract_cpu_hint(title),
            product_urls=target.product_urls,
            thumbnail_url=target.thumbnail_url,
            language_hint=language_hint,
            warnings=warnings,
        )

    # ── Text normalization ────────────────────────────────────────────────

    @staticmethod
    def _clean_text(value: str | None) -> str:
        if not value:
            return ""
        return _WHITESPACE_RE.sub(" ", value).strip()

    @staticmethod
    def _build_title_core(title: str) -> str:
        if not title:
            return ""
        clean = ModelNormalizer.clean_noisy_title(title)
        core = _TITLE_SEPARATOR_RE.split(clean, maxsplit=1)[0].strip()

        if "," in core:
            first_segment = core.split(",", maxsplit=1)[0].strip()
            if len(first_segment) >= 8:
                core = first_segment

        for noise in _RAW_NOISE_TERMS:
            core = re.sub(rf"\b{re.escape(noise)}\b", " ", core, flags=re.IGNORECASE)

        core = _WHITESPACE_RE.sub(" ", core).strip(" ,;|-")
        if len(core) > 120:
            core = core[:120].rsplit(" ", 1)[0].strip()
        return core

    # ── Brand / family / model derivation ─────────────────────────────────

    @staticmethod
    def _find_alias(text: str, aliases: dict[str, str]) -> str | None:
        normalized = normalize_lookup(text)
        if not normalized:
            return None
        for alias, canonical in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
                return canonical
        return None

    def _canonical_brand(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = normalize_lookup(value)
        if normalized in BRAND_ALIASES:
            return BRAND_ALIASES[normalized]
        return self._brand_from_text(value)

    def _brand_from_text(self, text: str) -> str | None:
        return self._find_alias(text, BRAND_ALIASES)

    def _canonical_family(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = normalize_lookup(value)
        if normalized in FAMILY_ALIASES:
            return FAMILY_ALIASES[normalized]
        return self._family_from_text(value)

    def _family_from_text(self, text: str) -> str | None:
        return self._find_alias(text, FAMILY_ALIASES)

    @staticmethod
    def _model_from_text(text: str, family: str) -> str | None:
        normalized = normalize_lookup(text)
        if not normalized:
            return None
        for alias, canonical in sorted(FAMILY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
            if canonical != family:
                continue
            match = re.search(
                rf"(?<!\w){re.escape(alias)}(?:\s+(?:pro|air|max))?\s*(\d{{1,2}})(?!\d)",
                normalized,
            )
            if match:
                return f"{family} {match.group(1)}"
        return family

    # ── SKU / MPN extraction ──────────────────────────────────────────────

    @staticmethod
    def _extract_tokens(texts: list[str]) -> dict[str, str | None]:
        merged: dict[str, str | None] = {
            "full_sku": None,
            "sub_model": None,
            "base_model": None,
            "mpn": None,
        }
        for text in texts:
            if not text:
                continue
            tokens = ModelNormalizer.extract_model_tokens(text)
            for key, value in tokens.items():
                if value and not merged[key]:
                    merged[key] = value
        return merged

    @staticmethod
    def _looks_like_model_code(value: str) -> bool:
        compact = value.strip().upper()
        if not _MODEL_CODE_RE.fullmatch(compact):
            return False
        return not ModelNormalizer.is_component_token(compact)

    @staticmethod
    def _looks_like_mpn(value: str) -> bool:
        compact = re.sub(r"[\s_-]+", "", value).upper()
        return bool(_MPN_COMPACT_RE.fullmatch(compact))

    @staticmethod
    def _looks_like_sku(value: str) -> bool:
        """Accept brand-agnostic model codes such as Lenovo ``83DV01HSED``."""
        compact = re.sub(r"[\s_-]+", "", value).upper()
        return (
            5 <= len(compact) <= 24
            and any(char.isalpha() for char in compact)
            and any(char.isdigit() for char in compact)
            and not ModelNormalizer.is_component_token(compact)
        )

    @staticmethod
    def _normalize_mpn(value: str | None) -> tuple[str | None, str | None]:
        if not value:
            return None, None
        cleaned = re.sub(r"[\s_]+", "", value.strip().upper())
        if not cleaned:
            return None, None

        if "-" in cleaned:
            parts = [part for part in cleaned.split("-") if part]
            if len(parts) == 2:
                return f"{parts[0]}-{parts[1]}", f"{parts[0]}{parts[1]}"
            display = "-".join(parts)
            return display, "".join(parts)

        if cleaned.startswith("90") and len(cleaned) >= 12:
            return f"{cleaned[:8]}-{cleaned[8:]}", cleaned
        return cleaned, cleaned

    def _resolve_mpn(
        self,
        target: ReviewTargetInput,
        token_mpn: str | None,
    ) -> tuple[str | None, str | None]:
        for value in (
            target.manufacturer_part_number,
            target.mpn,
            *target.mpns,
            token_mpn,
        ):
            display, compact = self._normalize_mpn(value)
            if display:
                return display, compact
        return None, None

    def _collect_sku_candidates(
        self,
        target: ReviewTargetInput,
        tokens: dict[str, str | None],
    ) -> tuple[str, ...]:
        provided = {value.strip().upper() for value in target.skus if value and value.strip()}

        values: list[str] = []
        for value in (
            *target.skus,
            tokens.get("full_sku"),
            tokens.get("sub_model"),
            tokens.get("base_model"),
        ):
            if not value:
                continue
            if value.strip().upper() not in provided and not self._looks_like_model_code(value):
                continue
            if value not in values:
                values.append(value)

        if (
            target.retailer_sku
            and self._looks_like_sku(target.retailer_sku)
            and not self._looks_like_mpn(target.retailer_sku)
            and target.retailer_sku not in values
        ):
            values.append(target.retailer_sku)
        return tuple(values)

    def _collect_mpn_candidates(
        self,
        target: ReviewTargetInput,
        tokens: dict[str, str | None],
    ) -> tuple[str, ...]:
        explicit_values = [
            target.manufacturer_part_number,
            target.mpn,
            *target.mpns,
            tokens.get("mpn"),
        ]
        explicit_compacts = {re.sub(r"[\s_-]+", "", value).upper() for value in explicit_values if value}

        values: list[str] = []
        for value in explicit_values:
            if not value:
                continue
            display, mpn_compact = self._normalize_mpn(value)
            for candidate in (display, mpn_compact):
                if candidate and candidate not in values:
                    values.append(candidate)

        if target.retailer_sku:
            compact = re.sub(r"[\s_-]+", "", target.retailer_sku).upper()
            if self._looks_like_mpn(target.retailer_sku) or compact in explicit_compacts:
                display, mpn_compact = self._normalize_mpn(target.retailer_sku)
                for candidate in (display, mpn_compact):
                    if candidate and candidate not in values:
                        values.append(candidate)
        return tuple(values)

    # ── CPU / language / diagnostics ──────────────────────────────────────

    @staticmethod
    def _extract_cpu_hint(text: str) -> str | None:
        if not text:
            return None
        intel = _INTEL_CPU_RE.search(text)
        if intel:
            return f"{intel.group(1).lower()}-{intel.group(2).upper()}"
        amd = _AMD_CPU_RE.search(text)
        if amd:
            return f"{amd.group(1).title()} {amd.group(2).upper()}"
        ultra = _ULTRA_CPU_RE.search(text)
        if ultra:
            return f"{ultra.group(1).title()} {ultra.group(2).upper()}"
        return None

    @staticmethod
    def _language_hint(text: str) -> str:
        arabic_count = len(_ARABIC_LETTER_RE.findall(text))
        total_letters = len(_LATIN_OR_ARABIC_LETTER_RE.findall(text))
        # Real Arabic titles often mix Arabic prose with Latin brand/model codes.
        # A low threshold catches those without misclassifying English-only titles.
        if total_letters and arabic_count / total_letters >= 0.15:
            return "ar"
        return "en"

    @staticmethod
    def _warnings(
        *,
        target: ReviewTargetInput,
        title: str,
        brand: str | None,
        family: str | None,
        model: str | None,
        sku_candidates: tuple[str, ...],
        mpn_candidates: tuple[str, ...],
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if not target.laptop_id and not target.canonical_id:
            warnings.append("missing_laptop_id")
        if not title:
            warnings.append("missing_title")
        if not brand:
            warnings.append("missing_brand")
        if not family and not model:
            warnings.append("missing_model")
        if not sku_candidates and not mpn_candidates:
            warnings.append("missing_exact_identifier")
        return tuple(warnings)

    @staticmethod
    def _target_key(
        *,
        target: ReviewTargetInput,
        brand: str | None,
        family: str | None,
        model: str | None,
        title_core: str,
        title: str,
        full_sku: str | None,
        mpn: str | None,
        sku_candidates: tuple[str, ...],
    ) -> str:
        if target.laptop_id:
            return target.laptop_id
        if target.canonical_id:
            return target.canonical_id

        basis = (
            mpn
            or full_sku
            or (sku_candidates[0] if sku_candidates else None)
            or "|".join(part for part in (brand, family, model, title_core or title) if part)
        )
        if not basis:
            basis = "unknown"
        digest = hashlib.sha1(basis.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
        return f"derived:{digest}"
