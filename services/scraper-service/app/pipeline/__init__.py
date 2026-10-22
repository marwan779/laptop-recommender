"""Laptop scraping and extraction pipeline.

Rebuilt from the ground up:
1. Scrapling engine scraping & raw artifact archival
2. Text sanitizer layer
3. CPU Anchor extraction via ground-truth CPU_SPECS
4. Deterministic extractor with Section-level envelope capture
5. Physical validation Gate 1
6. Unified AI fallback contract (GLiNER ONNX / NuExtract)
7. Physical validation Gate 2 (AI candidate re-validation)
"""

from app.pipeline.cpu_anchor import CPUAnchorExtractor
from app.pipeline.deterministic import DeterministicExtractor
from app.pipeline.envelope_normalizer import EnvelopePromptNormalizer
from app.pipeline.llm_auditor import FieldCorrection, GeminiAuditor, LLMAuditor, LLMProviderEndpoint
from app.pipeline.orchestrator import LaptopExtractionPipeline, PipelineResult
from app.pipeline.physical_validator import PhysicalValidator
from app.pipeline.raw_storage import RawScrapeStorage
from app.pipeline.sanitizer import TextSanitizer
from app.pipeline.schema import (
    EnvelopeResult,
    ExtractionEnvelope,
    RawScrapedProduct,
    empty_laptop_specifications,
)

__all__ = [
    "CPUAnchorExtractor",
    "DeterministicExtractor",
    "EnvelopePromptNormalizer",
    "EnvelopeResult",
    "ExtractionEnvelope",
    "FieldCorrection",
    "GeminiAuditor",
    "LLMAuditor",
    "LLMProviderEndpoint",
    "LaptopExtractionPipeline",
    "PipelineResult",
    "PhysicalValidator",
    "RawScrapeStorage",
    "RawScrapedProduct",
    "TextSanitizer",
    "empty_laptop_specifications",
]
