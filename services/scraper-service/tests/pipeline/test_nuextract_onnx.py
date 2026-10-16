"""Unit tests for NuExtractONNXFallbackExtractor (numind/NuExtract-v1.5).

Verifies:
1. Inheritance from IAIFallbackExtractor interface.
2. Prompt formatting following the official NuMind schema-text template.
3. Structured output parsing (JSON, markdown code blocks, key-value fallbacks).
4. End-to-end envelope extraction and batch processing.
"""

from unittest.mock import MagicMock, patch
import pytest

from pipeline.ai_fallback.base import IAIFallbackExtractor
from pipeline.ai_fallback.nuextract import NuExtractFallbackExtractor, NuExtractONNXFallbackExtractor
from pipeline.schema import EnvelopeResult, ExtractionEnvelope


def test_nuextract_onnx_implements_interface():
    """Verify NuExtractONNXFallbackExtractor implements IAIFallbackExtractor contract."""
    extractor = NuExtractONNXFallbackExtractor(lazy_load=True)
    assert isinstance(extractor, IAIFallbackExtractor)
    assert issubclass(NuExtractONNXFallbackExtractor, IAIFallbackExtractor)
    # Check backward compatibility alias
    assert NuExtractFallbackExtractor is NuExtractONNXFallbackExtractor
    assert "numind/NuExtract-2.0-2B" in extractor.model_name


def test_nuextract_official_prompt_formatting():
    """Verify prompt formatting matches official NuExtract template structure."""
    text = "NVIDIA GeForce RTX 4070 Laptop GPU 8GB GDDR6"
    field_name = "vram_gb"
    prompt = NuExtractONNXFallbackExtractor.format_prompt(text=text, field_name=field_name)

    assert "<|input|>" in prompt
    assert "### Template:" in prompt
    assert '"vram_gb": null' in prompt
    assert "### Text:" in prompt
    assert text in prompt
    assert "<|output|>" in prompt


def test_nuextract_parse_extracted_value_clean_json():
    """Verify parsing clean JSON output."""
    raw = '{\n  "vram_gb": "8GB GDDR6"\n}'
    val = NuExtractONNXFallbackExtractor._parse_extracted_value(raw, "vram_gb")
    assert val == "8GB GDDR6"


def test_nuextract_parse_extracted_value_with_value_key():
    """Verify parsing output when key is generic 'value'."""
    raw = '{"value": "16GB DDR5"}'
    val = NuExtractONNXFallbackExtractor._parse_extracted_value(raw, "capacity_gb")
    assert val == "16GB DDR5"


def test_nuextract_parse_extracted_value_markdown_fenced():
    """Verify parsing output wrapped in markdown ```json code blocks."""
    raw = """```json
{
  "battery_cells": 4
}
```"""
    val = NuExtractONNXFallbackExtractor._parse_extracted_value(raw, "battery_cells")
    assert val == 4


def test_nuextract_parse_extracted_value_empty_and_null():
    """Verify null and empty outputs return None."""
    assert NuExtractONNXFallbackExtractor._parse_extracted_value("", "wifi") is None
    assert NuExtractONNXFallbackExtractor._parse_extracted_value("{}", "wifi") is None
    assert NuExtractONNXFallbackExtractor._parse_extracted_value('{"wifi": null}', "wifi") is None


def test_extract_envelope_with_mocked_generator():
    """Verify extract_envelope and batch_extract_envelopes with simulated model generation."""
    extractor = NuExtractONNXFallbackExtractor(lazy_load=True)
    # Inject loaded mock state
    extractor._backend = "onnx-mock"
    extractor._generate_onnx_genai = MagicMock(return_value='{"refresh_rate_hz": 144}')
    extractor._genai_model = MagicMock()

    envelope = ExtractionEnvelope(
        field_path="display.refresh_rate_hz",
        field_description="Display refresh rate in Hz",
        raw_context="15.6-inch FHD 144Hz IPS display",
        failure_reason="missing_key",
        expected_type="int",
    )

    res = extractor.extract_envelope(envelope)
    assert isinstance(res, EnvelopeResult)
    assert res.field_path == "display.refresh_rate_hz"
    assert res.extracted_value == 144
    assert res.confidence == 0.9
    assert "numind/NuExtract-2.0-2B" in res.model_name

    # Test batch extraction
    batch_res = extractor.batch_extract_envelopes([envelope, envelope])
    assert len(batch_res) == 2
    assert batch_res[0].extracted_value == 144
    assert batch_res[1].extracted_value == 144


def test_extract_envelope_empty_context():
    """Verify empty context returns early with None without invoking generation."""
    extractor = NuExtractONNXFallbackExtractor(lazy_load=True)
    envelope = ExtractionEnvelope(
        field_path="gpu.vram_gb",
        field_description="GPU VRAM",
        raw_context="",
        failure_reason="missing_key",
        expected_type="str",
    )
    res = extractor.extract_envelope(envelope)
    assert res.extracted_value is None
    assert res.confidence == 0.0
