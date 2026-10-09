"""GLiNER Model Wrapper.

Provides an interface for loading and running GLiNER models
(e.g., urchade/gliner_base-v2.1) for zero-shot named entity recognition.
"""

from __future__ import annotations

import logging
import time
from typing import Any

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
            model_name: Hugging Face model identifier (e.g. urchade/gliner_base-v2.1).
            device: 'cuda', 'cpu', or None for auto-detection.
            lazy_load: If True, defer model loading until first extraction.
        """
        self.model_name = model_name
        self._device = device
        self._model = None

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
        """Extract entity spans from text.

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

        self._ensure_loaded()

        try:
            # GLiNER predict_entities
            entities = self._model.predict_entities(
                text,
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
        max_chunk_chars: int = 1800,
    ) -> list[dict[str, Any]]:
        """Extract entities from full specification table and title.

        Builds structured text blocks. If total content is large, chunks it
        intelligently by spec sections to prevent DeBERTa token truncation,
        then merges all extracted spans.

        Args:
            title: Product title.
            specs: Dictionary of scraped raw spec table key-values.
            labels: Target entity labels.
            threshold: Confidence threshold.
            max_chunk_chars: Max characters per chunk before splitting.

        Returns:
            Merged list of extracted entity dictionaries.
        """
        lines = [f"Product Title: {title}"] if title else []
        for k, v in specs.items():
            if v and str(v).strip():
                lines.append(f"{k}: {v}")

        # If total lines are under threshold, run in one single forward pass
        full_text = "\n".join(lines)
        if len(full_text) <= max_chunk_chars:
            return self.extract_entities(full_text, labels, threshold=threshold)

        # Chunk lines preserving section context
        chunks: list[str] = []
        current_chunk_lines: list[str] = [lines[0]] if lines else []
        current_len = len(lines[0]) if lines else 0

        for line in lines[1:]:
            if current_len + len(line) + 1 > max_chunk_chars and current_chunk_lines:
                chunks.append("\n".join(current_chunk_lines))
                # Add title context to subsequent chunks for entity disambiguation
                current_chunk_lines = [lines[0], line] if lines else [line]
                current_len = len(lines[0]) + len(line) + 1 if lines else len(line)
            else:
                current_chunk_lines.append(line)
                current_len += len(line) + 1

        if current_chunk_lines:
            chunks.append("\n".join(current_chunk_lines))

        # Run extraction on all chunks and combine
        all_entities: list[dict[str, Any]] = []
        seen_spans: set[tuple[str, str]] = set()

        for chunk in chunks:
            chunk_ents = self.extract_entities(chunk, labels, threshold=threshold)
            for ent in chunk_ents:
                span_key = (ent["label"], ent["text"].strip().lower())
                if span_key not in seen_spans:
                    seen_spans.add(span_key)
                    all_entities.append(ent)

        return all_entities

