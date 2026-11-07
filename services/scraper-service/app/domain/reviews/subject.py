"""Pure helpers for deriving a search "subject" from a review target.

Shared by the YouTube and community query builders so identity cleaning is
implemented once. Zero I/O — unit-testable in isolation.
"""

from __future__ import annotations

import re

from app.schemas.events import LaptopReviewTarget

_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    """Trim and collapse internal whitespace."""
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", str(value)).strip()


def clean_model(model: str | None, family: str, brand: str = "") -> str:
    """Remove repeated brand/family prefixes from a model string.

    Guarantees queries like ``"LOQ LOQ 15IRX9"`` or
    ``"HP Victus HP Victus 15-fa2352TX"`` are never produced.
    """
    cleaned = clean_text(model)
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


def join_subject(brand: str, family: str, model: str) -> str:
    """Join identity parts without duplicating tokens."""
    parts: list[str] = []
    seen: set[str] = set()

    for part in (brand, family, model):
        if not part:
            continue
        key = part.lower()
        if key in seen:
            continue
        # Skip a part already contained in the previous part
        # (e.g. family "LOQ" inside model "LOQ 15IRX9").
        if parts and key in parts[-1].lower():
            continue
        seen.add(key)
        parts.append(part)

    return _WHITESPACE_RE.sub(" ", " ".join(parts)).strip()


def build_subject(target: LaptopReviewTarget) -> str:
    """Return the cleaned ``brand family model`` subject for a target.

    Never returns an empty string: falls back to the canonical id, then the
    laptop id, then a generic ``"laptop"``.
    """
    brand = clean_text(target.brand)
    family = clean_text(target.laptop_family)
    model = clean_model(target.laptop_model, family, brand)

    subject = join_subject(brand, family, model)
    if subject:
        return subject
    return clean_text(target.canonical_id) or clean_text(target.laptop_id) or "laptop"


__all__ = ["build_subject", "clean_model", "clean_text", "join_subject"]
