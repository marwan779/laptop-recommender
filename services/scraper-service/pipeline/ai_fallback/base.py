"""Abstract base contract for AI Fallback Extractors.

Provides a unified interface for plug-and-play AI backends
(GLiNER ONNX, NuExtract, Ollama LLM, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Sequence

from pipeline.schema import (
    ComponentEnvelope,
    ComponentEnvelopeResult,
    EnvelopeResult,
    ExtractionEnvelope,
)


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

    def extract_component_envelope(
        self, envelope: ComponentEnvelope
    ) -> ComponentEnvelopeResult:
        """Process a component envelope (filling null fields in sub_schema)."""
        extracted = {}
        for f_name, f_val in envelope.sub_schema.items():
            if f_name in envelope.locked_fields:
                continue
            field_path = f"{envelope.component_name}.{f_name}"
            scalar_env = ExtractionEnvelope(
                field_path=field_path,
                field_description=envelope.field_descriptions.get(f_name, f_name),
                raw_context=envelope.raw_spec,
                failure_reason="missing_key",
                expected_type="str",
                allowed_values=envelope.enum_constraints.get(f_name),
                cpu_context=envelope.cpu_context,
            )
            res = self.extract_envelope(scalar_env)
            extracted[f_name] = res.extracted_value

        return ComponentEnvelopeResult(
            component_name=envelope.component_name,
            extracted_fields=extracted,
            model_name=self.model_name,
        )

    def batch_extract_component_envelopes(
        self, envelopes: Sequence[ComponentEnvelope]
    ) -> List[ComponentEnvelopeResult]:
        """Process a batch of component envelopes."""
        return [self.extract_component_envelope(e) for e in envelopes]

    @abstractmethod
    def health_check(self) -> bool:
        """Verify that the model weights or backend service are initialized and healthy."""
        ...

