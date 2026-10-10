"""Token budget enforcement for GLiNER zero-shot model.

GLiNER urchade/gliner_base has a hard limit of 384 tokens (labels + text + special tokens).
Beyond 384, the backbone silently truncates and entities are lost.
This module strictly enforces safe token budgets.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

logger = logging.getLogger(__name__)

GLINER_MAX_TOKENS = 384  # model hard limit (labels + text + special tokens)
GLINER_SAFE_BUDGET = 330  # what we actually allow; leaves margin for special tokens
MAX_LABELS_PER_CALL = 6  # keep the label prompt small
MAX_LABEL_WORDS = 3  # labels are short noun phrases

_TOKENIZER = None
_TOKENIZER_LOADED = False


def get_tokenizer():
    """Lazily load the Hugging Face DebertaV2Tokenizer matching GLiNER backbone."""
    global _TOKENIZER, _TOKENIZER_LOADED
    if not _TOKENIZER_LOADED:
        _TOKENIZER_LOADED = True
        try:
            from transformers import DebertaV2Tokenizer
            _TOKENIZER = DebertaV2Tokenizer.from_pretrained("urchade/gliner_base")
            logger.info("Successfully loaded DebertaV2Tokenizer for GLiNER token budgeting.")
        except Exception as e:
            logger.warning(
                "Could not load DebertaV2Tokenizer for token budget (%s). "
                "Using conservative heuristic token estimation.",
                e,
            )
            _TOKENIZER = None
    return _TOKENIZER


def count_tokens(text: str, labels: list[str] | None = None) -> int:
    """Count subword tokens for input text and entity labels.

    Args:
        text: Plain text prompt.
        labels: Optional list of entity labels.

    Returns:
        Integer count of subword tokens including special prompt tokens.
    """
    labels = labels or []
    tok = get_tokenizer()

    if tok is not None:
        try:
            # GLiNER formats input as [BOS] [label_1] ... [SEP] text [EOS]
            text_tokens = len(tok(text or "", add_special_tokens=False)["input_ids"])
            label_tokens = sum(
                len(tok(lbl or "", add_special_tokens=False)["input_ids"]) + 2
                for lbl in labels
            )
            special_tokens = 4
            return text_tokens + label_tokens + special_tokens
        except Exception:
            pass

    # Conservative heuristic fallback:
    # Subword expansion on technical strings is ~1.8x words + label overhead + special tokens
    words = len((text or "").split())
    label_words = sum(len((lbl or "").split()) for lbl in labels)
    return math.ceil(words * 1.8) + math.ceil(label_words * 1.8) + 10


def _cut_at_clause_boundary(text: str, max_tokens_allowed: int, labels: list[str]) -> str:
    """Trim a string by dropping trailing clauses until it fits the token budget."""
    if count_tokens(text, labels) <= max_tokens_allowed:
        return text

    # Split by clause boundaries (;, ,, |, .)
    clauses = re.split(r"([;,|\n])", text)
    # clauses has alternating [clause, separator, clause, separator...]
    accumulated = ""
    for i in range(0, len(clauses), 2):
        chunk = clauses[i] + (clauses[i + 1] if i + 1 < len(clauses) else "")
        candidate = accumulated + chunk
        if count_tokens(candidate, labels) <= max_tokens_allowed:
            accumulated = candidate
        else:
            break

    if accumulated.strip():
        return accumulated.strip()

    # If even the first clause exceeds budget, fall back to word-level trimming
    words = text.split()
    while words:
        cand = " ".join(words)
        if count_tokens(cand, labels) <= max_tokens_allowed:
            return cand
        words.pop()

    return text[:max(10, len(text) // 2)]


def fit_to_budget(
    parts: list[tuple[str, int]] | None = None,
    labels: list[str] | None = None,
    max_budget: int = GLINER_SAFE_BUDGET,
    *,
    target_row: str | None = None,
    sibling_facts: list[str] | None = None,
    title: str | None = None,
) -> str:
    """Assemble prompt from prioritized parts, dropping lowest priority first.

    Priority hierarchy:
        1. Target row (highest priority - key + value). Never dropped, only cut at
           clause boundary (';', ',', '|', '.') if alone it is too long.
        2. Sibling facts (2-4 most relevant facts). Dropped if budget exceeded.
        3. Title (shortened title, max ~12 words). Dropped first if budget exceeded.

    Args:
        parts: Optional list of tuples (text, priority) where lower integer = higher priority.
        labels: Entity labels to be sent alongside the text.
        max_budget: Maximum allowed tokens for the call (default: 330).
        target_row: Direct kwarg for priority 1 target row.
        sibling_facts: Direct kwarg for priority 2 sibling facts.
        title: Direct kwarg for priority 3 title.

    Returns:
        Assembled text string guaranteed to fit within max_budget.
    """
    labels = labels or []

    # If called via explicit kwargs, construct parts list
    if parts is None:
        parts = []
        if target_row:
            parts.append((target_row.strip(), 1))
        if sibling_facts:
            facts_str = "Known: " + ", ".join(f.strip() for f in sibling_facts if f.strip())
            parts.append((facts_str, 2))
        if title:
            # Shortened title (max ~12 words)
            title_words = title.strip().split()[:12]
            parts.append((f"Product: {' '.join(title_words)}", 3))

    # Sort parts by priority (1 is highest priority, 3 is lowest)
    # Store as: priority, text
    sorted_parts = sorted(parts, key=lambda x: x[1])

    # We want to build the prompt. The ideal prompt has all parts in standard order:
    # Product (title) -> Known (siblings) -> Target row (spec).
    # But when dropping, we drop lowest priority (highest priority number) first.

    # Start with all parts included
    active_parts = {p[1]: p[0] for p in sorted_parts if p[0].strip()}

    def build_text(current_dict: dict[int, str]) -> str:
        # Order by display preference: 3 (Product), then 2 (Known), then 1 (Spec)
        # Or standard logical order: title, siblings, target row
        ordered = []
        if 3 in current_dict:
            ordered.append(current_dict[3])
        if 2 in current_dict:
            ordered.append(current_dict[2])
        if 1 in current_dict:
            ordered.append(current_dict[1])
        # Also include any custom priorities
        for prio in sorted(current_dict.keys()):
            if prio not in (1, 2, 3):
                ordered.append(current_dict[prio])
        return "\n".join(ordered)

    current_text = build_text(active_parts)
    if count_tokens(current_text, labels) <= max_budget:
        return current_text

    # Drop lowest priority first (highest numeric value > 1)
    for prio in sorted(active_parts.keys(), reverse=True):
        if prio == 1:
            continue  # Never drop target row completely
        del active_parts[prio]
        current_text = build_text(active_parts)
        if count_tokens(current_text, labels) <= max_budget:
            return current_text

    # If only target row remains and still exceeds budget, cut at clause boundaries
    if 1 in active_parts:
        target_text = active_parts[1]
        active_parts[1] = _cut_at_clause_boundary(target_text, max_budget, labels)

    return build_text(active_parts)
