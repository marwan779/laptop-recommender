"""GLiNER Model Wrapper with Strict Token Budget Enforcement.

Provides an interface for loading and running GLiNER models
(e.g., urchade/gliner_base) for zero-shot named entity recognition,
strictly enforcing token budgets (<= 384 tokens hard limit, <= 330 safe budget).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from gliner_extractor.token_budget import (
    GLINER_MAX_TOKENS,
    GLINER_SAFE_BUDGET,
    MAX_LABELS_PER_CALL,
    count_tokens,
    fit_to_budget,
)

logger = logging.getLogger(__name__)


class GLiNERExtractor:
    """Wrapper around GLiNER model for zero-shot hardware specification extraction."""

    def __init__(
        self,
        model_name: str = "urchade/gliner_base",
        device: str | None = None,
        lazy_load: bool = False,
    ) -> None:
        """Initialize the GLiNER extractor.

        Args:
            model_name: Hugging Face model identifier (e.g. urchade/gliner_base).
            device: 'cuda', 'cpu', or None for auto-detection.
            lazy_load: If True, defer model loading until first extraction.
        """
        self.model_name = model_name
        self._device = device
        self._model = None
        self.max_tokens_seen: int = 0
        self.truncations_prevented: int = 0

        if not lazy_load:
            self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        """Load the model if not already loaded."""
        if self._model is not None:
            return

        import torch
        from gliner import GLiNER

        if self._device is None:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info("Loading GLiNER model '%s' on %s...", self.model_name, self._device)
        start_t = time.perf_counter()

        self._model = GLiNER.from_pretrained(self.model_name)
        self._model.to(self._device)
        self._model.eval()

        load_sec = time.perf_counter() - start_t
        logger.info("GLiNER model loaded successfully in %.2fs", load_sec)

    @property
    def model(self):
        self._ensure_loaded()
        return self._model

    def extract_entities(
        self,
        text: str,
        labels: list[str],
        threshold: float = 0.35,
        flat_ner: bool = True,
    ) -> list[dict[str, Any]]:
        """Extract entity spans from text while strictly respecting token budget.

        Args:
            text: Input plain text.
            labels: List of target entity label names.
            threshold: Confidence score threshold (0.0 - 1.0).
            flat_ner: If True, resolves overlapping spans keeping highest score.

        Returns:
            List of dicts: [{'text': str, 'label': str, 'score': float, 'start': int, 'end': int}, ...]
        """
        if not text or not labels:
            return []

        # If labels exceed MAX_LABELS_PER_CALL (6), chunk them into batches
        if len(labels) > MAX_LABELS_PER_CALL:
            all_ents: list[dict[str, Any]] = []
            seen_spans: set[tuple[str, str]] = set()
            for i in range(0, len(labels), MAX_LABELS_PER_CALL):
                batch_labels = labels[i : i + MAX_LABELS_PER_CALL]
                ents = self.extract_entities(
                    text,
                    batch_labels,
                    threshold=threshold,
                    flat_ner=flat_ner,
                )
                for ent in ents:
                    k = (ent.get("label", ""), ent.get("text", "").strip().lower())
                    if k not in seen_spans:
                        seen_spans.add(k)
                        all_ents.append(ent)
            return all_ents

        # Token guard: check if prompt fits within hard budget (384 tokens)
        cur_tokens = count_tokens(text, labels)
        if cur_tokens > self.max_tokens_seen:
            self.max_tokens_seen = cur_tokens

        prompt_text = text
        if cur_tokens > GLINER_SAFE_BUDGET:
            # Fit prompt text to safe budget
            prompt_text = fit_to_budget(
                target_row=text,
                labels=labels,
                max_budget=GLINER_SAFE_BUDGET,
            )
            self.truncations_prevented += 1
            new_tokens = count_tokens(prompt_text, labels)
            logger.debug(
                "Prevented GLiNER truncation: reduced tokens from %d to %d",
                cur_tokens,
                new_tokens,
            )

        self._ensure_loaded()

        try:
            entities = self._model.predict_entities(
                prompt_text,
                labels,
                threshold=threshold,
                flat_ner=flat_ner,
            )
            return entities
        except Exception as e:
            logger.error("Error during GLiNER extraction: %s", e)
            return []

    def extract_from_spec_blocks(
        self,
        title: str,
        specs: dict[str, str],
        labels: list[str],
        threshold: float = 0.35,
        max_chunk_tokens: int = GLINER_SAFE_BUDGET,
    ) -> list[dict[str, Any]]:
        """Extract entities from full specification table and title using token chunking.

        Builds structured text blocks. Chunks strictly by subword token budget
        to eliminate silent DeBERTa token truncation.

        Args:
            title: Product title.
            specs: Dictionary of scraped raw spec table key-values.
            labels: Target entity labels.
            threshold: Confidence threshold.
            max_chunk_tokens: Max subword tokens per chunk (default: 330).

        Returns:
            Merged list of extracted entity dictionaries.
        """
        lines = [f"Product Title: {title}"] if title else []
        for k, v in specs.items():
            if v and str(v).strip():
                lines.append(f"{k}: {v}")

        if not lines:
            return []

        title_header = lines[0] if title else ""
        spec_lines = lines[1:] if title else lines

        # Chunk lines strictly enforcing token budget
        chunks: list[str] = []
        current_lines: list[str] = [title_header] if title_header else []

        for line in spec_lines:
            test_lines = current_lines + [line]
            test_text = "\n".join(test_lines)
            if count_tokens(test_text, labels[:MAX_LABELS_PER_CALL]) > max_chunk_tokens and current_lines:
                chunks.append("\n".join(current_lines))
                # Add title context to subsequent chunk
                current_lines = [title_header, line] if title_header else [line]
            else:
                current_lines.append(line)

        if current_lines:
            chunks.append("\n".join(current_lines))

        # Run extraction across all chunks
        all_entities: list[dict[str, Any]] = []
        seen_spans: set[tuple[str, str]] = set()

        for chunk in chunks:
            chunk_ents = self.extract_entities(chunk, labels, threshold=threshold)
            for ent in chunk_ents:
                span_key = (ent.get("label", ""), ent.get("text", "").strip().lower())
                if span_key not in seen_spans:
                    seen_spans.add(span_key)
                    all_entities.append(ent)

        return all_entities
