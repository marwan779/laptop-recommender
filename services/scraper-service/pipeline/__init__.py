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

from pipeline.cpu_anchor import CPUAnchorExtractor
from pipeline.deterministic import DeterministicExtractor
from pipeline.envelope_normalizer import EnvelopePromptNormalizer
from pipeline.llm_auditor import FieldCorrection, GeminiAuditor, LLMAuditor, LLMProviderEndpoint
from pipeline.orchestrator import LaptopExtractionPipeline, PipelineResult
from pipeline.physical_validator import PhysicalValidator
from pipeline.raw_storage import RawScrapeStorage
from pipeline.sanitizer import TextSanitizer
from pipeline.schema import (
    EnvelopeResult,
    ExtractionEnvelope,
    RawScrapedProduct,
    empty_laptop_specifications,
)

__all__ = [
    "LaptopExtractionPipeline",
    "PipelineResult",
    "TextSanitizer",
    "CPUAnchorExtractor",
    "DeterministicExtractor",
    "EnvelopePromptNormalizer",
    "PhysicalValidator",
    "LLMAuditor",
    "LLMProviderEndpoint",
    "GeminiAuditor",
    "FieldCorrection",
    "RawScrapeStorage",
    "ExtractionEnvelope",
    "EnvelopeResult",
    "RawScrapedProduct",
    "empty_laptop_specifications",
]

