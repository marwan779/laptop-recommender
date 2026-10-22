"""AI Fallback module providing unified interfaces and model adapters."""

from pipeline.ai_fallback.base import IAIFallbackExtractor
from pipeline.ai_fallback.gliner_onnx import GLiNERONNXFallbackExtractor
from pipeline.ai_fallback.nuextract import NuExtractFallbackExtractor, NuExtractONNXFallbackExtractor

__all__ = [
    "IAIFallbackExtractor",
    "GLiNERONNXFallbackExtractor",
    "NuExtractFallbackExtractor",
    "NuExtractONNXFallbackExtractor",
]
