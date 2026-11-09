"""Pure helpers for normalizing bilingual community review text."""

from __future__ import annotations

from collections.abc import Iterable


def _clean_list(values: Iterable[object] | None) -> list[str]:
    if not values:
        return []
    return [str(value).strip() for value in values if value is not None and str(value).strip()]


def align_bilingual_lists(
    en_list: Iterable[object] | None,
    ar_list: Iterable[object] | None,
) -> tuple[list[str], list[str]]:
    """Keep English review lists 1:1 with their verified Arabic counterparts.

    The first ``len(ar_list)`` English items are the hardware-verified
    translations of the Arabic list. Any trailing English items are
    family-level editorial tags that may describe a different SKU, so they are
    dropped whenever both lists are non-empty and English is longer.
    """
    english = _clean_list(en_list)
    arabic = _clean_list(ar_list)

    if english and arabic and len(english) > len(arabic):
        english = english[: len(arabic)]

    return english, arabic


__all__ = ["align_bilingual_lists"]
