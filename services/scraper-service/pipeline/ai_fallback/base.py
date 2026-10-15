"""Abstract base contract for AI Fallback Extractors.

Provides a unified interface for plug-and-play AI backends
(GLiNER ONNX, NuExtract, Ollama LLM, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Sequence

from pipeline.schema import EnvelopeResult, ExtractionEnvelope


class IAIFallbackExtractor(ABC):
    """Unified contract that all AI fallback models must implement."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the identifier of the active AI model/backend."""
        ...

    @abstractmethod
    def extract_envelope(self, envelope: ExtractionEnvelope) -> EnvelopeResult:
        """Process a single field extraction envelope and return candidate extraction."""
        ...

    @abstractmethod
    def batch_extract_envelopes(
        self, envelopes: Sequence[ExtractionEnvelope]
    ) -> List[EnvelopeResult]:
        """Process a batch of envelopes together for optimal throughput."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Verify that the model weights or backend service are initialized and healthy."""
        ...

