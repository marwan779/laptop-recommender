"""End-to-end and component tests for the rebuilt 7-layer extraction pipeline."""

import pytest
from pipeline.ai_fallback.base import IAIFallbackExtractor
from pipeline.cpu_anchor import CPUAnchorExtractor
from pipeline.deterministic import DeterministicExtractor
from pipeline.orchestrator import LaptopExtractionPipeline, PipelineResult
from pipeline.physical_validator import PhysicalValidator
from pipeline.sanitizer import TextSanitizer
from pipeline.schema import (
    EnvelopeResult,
    ExtractionEnvelope,
    RawScrapedProduct,
)


class MockAIExtractor(IAIFallbackExtractor):
    """Mock AI extractor for testing envelope resolution and Gate 2 validation."""

    def __init__(self, return_values: dict = None) -> None:
        self.return_values = return_values or {}

    @property
    def model_name(self) -> str:
        return "mock-ai-v1"

    def health_check(self) -> bool:
        return True

    def extract_envelope(self, envelope: ExtractionEnvelope) -> EnvelopeResult:
        val = self.return_values.get(envelope.field_path)
        return EnvelopeResult(
            field_path=envelope.field_path,
            extracted_value=val,
            raw_span=str(val) if val is not None else None,
            confidence=0.95,
            model_name=self.model_name,
        )

    def batch_extract_envelopes(self, envelopes) -> list:
        return [self.extract_envelope(env) for env in envelopes]


# =============================================================================
# 1. Layer 2: Text Sanitizer Tests
# =============================================================================
def test_sanitizer_cleans_unicode_trademarks_footnotes():
    raw = "Lenovo Legion Pro 5™®\u200e ( 1 ) 16IRX8 1 2 3"
    cleaned = TextSanitizer.clean_text(raw)
    assert "™" not in cleaned
    assert "®" not in cleaned
    assert "\u200e" not in cleaned
    assert "Lenovo Legion Pro 5" in cleaned
    assert not cleaned.endswith("1 2 3")


def test_sanitizer_identifies_placeholders():
    assert TextSanitizer.is_placeholder("TBD")
    assert TextSanitizer.is_placeholder("N/A")
    assert TextSanitizer.is_placeholder("Varies by model")
    assert TextSanitizer.is_placeholder("--")
    assert not TextSanitizer.is_placeholder("Intel Core i7-13620H")


# =============================================================================
# 2. Layer 3: CPU Anchor Extractor Tests
# =============================================================================
def test_cpu_anchor_identifies_sku_and_constraints():
    extractor = CPUAnchorExtractor()
    title = "ASUS ROG Strix G16 G614JV - Intel Core i7-13620H - 16GB DDR5 - RTX 4060"
    cpu_specs, constraints, key = extractor.extract(title=title)

    assert key == "intel_core_i7_13620h"
    assert cpu_specs["manufacturer"] == "Intel"
    assert cpu_specs["model"] == "Core i7-13620H"
    assert cpu_specs["cores"] == 10
    assert cpu_specs["threads"] == 16
    assert constraints["max_memory_gb"] == 96
    assert "DDR5" in constraints["supported_memory"]


# =============================================================================
# 3. Layer 5 & 7: Physical Validator Tests
# =============================================================================
def test_validator_hardware_bounds_and_cpu_constraints():
    # Valid RAM
    valid, val, _ = PhysicalValidator.validate_memory_capacity(16, {"max_memory_gb": 64})
    assert valid and val == 16

    # RAM exceeding CPU max capacity
    valid, _, reason = PhysicalValidator.validate_memory_capacity(128, {"max_memory_gb": 64})
    assert not valid
    assert "exceeds_cpu_max" in reason

    # Incompatible RAM type (DDR4 on DDR5-only chip)
    valid, _, reason = PhysicalValidator.validate_memory_type("DDR4", {"supported_memory": ["DDR5", "LPDDR5X"]})
    assert not valid
    assert "incompatible_with_cpu" in reason

    # FAA battery limit (strictly <= 99.9 Wh)
    valid, val, _ = PhysicalValidator.validate_battery_capacity(90.0)
    assert valid and val == 90.0

    valid, _, reason = PhysicalValidator.validate_battery_capacity(120.0)
    assert not valid
    assert "out_of_bounds" in reason


# =============================================================================
# 4. Layer 4: Deterministic Extractor & Section Envelope Tests (Option B)
# =============================================================================
def test_deterministic_extractor_captures_section_envelopes():
    extractor = DeterministicExtractor()
    title = "Acer Nitro 5 AN515 - Core i7-13620H - RTX 4050"
    table = {
        "RAM": "16GB DDR5",
        "Storage": "512GB SSD",
    }
    sections = {
        "Display Section": "15.6 inch diagonal screen with vibrant colors, ultra-slim bezel, 144Hz high refresh rate."
    }

    specs, envelopes = extractor.extract(
        title=title,
        sanitized_table=table,
        sanitized_sections=sections,
    )

    # Deterministic extractions
    assert specs["memory"]["capacity_gb"] == 16
    assert specs["memory"]["memory_type"] == "DDR5"
    assert specs["storage"]["capacity_gb"] == 512
    assert specs["gpu"]["manufacturer"] == "NVIDIA"
    assert specs["display"]["size_inches"] == 15.6

    # Missing battery was packaged into envelope with section context
    battery_env = next((e for e in envelopes if e.field_path == "power_battery.battery_capacity_wh"), None)
    assert battery_env is not None
    assert battery_env.section_name == "Battery & Power"


# =============================================================================
# 5. Full 7-Layer Orchestrator Test (with Gate 2 Re-validation)
# =============================================================================
def test_full_pipeline_orchestration_and_gate2_safety():
    # Setup mock AI that returns:
    # 1. A valid battery capacity (80.0 Wh)
    # 2. An INVALID display size (28.0 inches - e.g. a hallucination or monitor spec)
    mock_ai = MockAIExtractor(
        return_values={
            "power_battery.battery_capacity_wh": 80.0,
            "display.size_inches": 28.0,  # Physically impossible for a laptop!
        }
    )

    pipeline = LaptopExtractionPipeline(ai_fallback=mock_ai)

    raw_product = RawScrapedProduct(
        url="https://example.com/laptop/123",
        store="CompuMarts",
        title="Dell G15 5530 Gaming Laptop - Intel Core i7-13620H - RTX 4060 - 16GB DDR5",
        raw_html="<html></html>",
        raw_tables={
            "specs": {
                "Storage": "1TB SSD NVMe",
                "Power": "330W Adapter",
            }
        },
        raw_sections={
            "Battery & Power": "Integrated multi-cell lithium battery with express charge.",
            "Display": "Vibrant gaming display.",
        },
    )

    result = pipeline.process_raw_product(raw_product)

    # 1. CPU verified ground truth (Option A)
    assert result.specs["cpu"]["model"] == "Core i7-13620H"
    assert result.specs["cpu"]["cores"] == 10

    # 2. Memory & GPU verified
    assert result.specs["memory"]["capacity_gb"] == 16
    assert result.specs["gpu"]["model"] == "GeForce RTX 4060"

    # 3. AI resolved battery accepted by Gate 2
    assert result.specs["power_battery"]["battery_capacity_wh"] == 80.0

    # 4. AI hallucinated 28.0" display REJECTED by Gate 2!
    assert result.specs["display"]["size_inches"] is None
    rejections = [r for r in result.validation_rejections if r["field_path"] == "display.size_inches"]
    assert len(rejections) > 0
    assert rejections[0]["gate"] == 2
    assert "out_of_bounds" in rejections[0]["reason"]


# =============================================================================
# 7. Identity & Title Prefix Envelope Tests
# =============================================================================
def test_identity_extraction_hp_victus():
    """Verify clean identity extraction on HP Victus title."""
    pipeline = LaptopExtractionPipeline()
    raw = RawScrapedProduct(
        url="https://example.com/hp-victus",
        store="compumarts",
        title="HP Victus 15 15-fa2082wm Gaming Laptop – Intel Core i5-13420H 13th Gen, 16GB RAM, 512GB SSD, RTX 4050, 15.6″ FHD 144Hz IPS, Windows 11 Home – Mica Silver",
        raw_html="",
        raw_tables={"specs": {"Color": "Mica Silver"}},
        raw_sections={},
        price=52999.0,
    )
    result = pipeline.process_raw_product(raw)
    ident = result.specs["identity"]
    assert ident["brand"] == "HP"
    assert ident["laptop_family"] == "Victus"
    assert ident["laptop_model"] == "Victus 15"
    assert ident["manufacturer_part_number"] == "15-fa2082wm"
    assert ident["color"] == "Mica Silver"


def test_identity_envelope_contains_only_clean_laptop_name():
    """Verify that when identity is missing, envelope contains ONLY clean laptop name."""
    pipeline = LaptopExtractionPipeline()
    raw = RawScrapedProduct(
        url="https://example.com/exotic",
        store="compumarts",
        title="ExoticBrand TitanX TX-9900 Gaming Laptop – Intel Core i5-13420H, 16GB RAM, 512GB SSD, RTX 4050",
        raw_html="",
        raw_tables={"specs": {}},
        raw_sections={},
        price=30000.0,
    )
    result = pipeline.process_raw_product(raw)
    family_envelopes = [e for e in result.envelopes_generated if e.field_path == "identity.laptop_family"]
    assert len(family_envelopes) == 1
    # MUST contain only the clean laptop name!
    assert family_envelopes[0].raw_context == "ExoticBrand TitanX TX-9900 Gaming Laptop"
    # MUST NOT contain trailing specs!
    assert "Intel Core" not in family_envelopes[0].raw_context
    assert "16GB RAM" not in family_envelopes[0].raw_context


# =============================================================================
# 8. Provenance Audit Logging Tests
# =============================================================================
def test_provenance_audit_trace_diagnoses_populated_and_empty_fields():
    """Verify that provenance tracker accurately records layer origins and empty field causality."""
    mock_ai = MockAIExtractor(
        return_values={
            "display.size_inches": 32.0,  # Physically impossible -> Gate 2 will reject!
        }
    )
    pipeline = LaptopExtractionPipeline(ai_fallback=mock_ai)
    raw = RawScrapedProduct(
        url="https://example.com/laptop-prov-test",
        store="compumarts",
        title="HP Victus 15 15-fa2082wm Gaming Laptop – Intel Core i5-13420H 13th Gen, 16GB RAM, 512GB SSD, RTX 4050",
        raw_html="",
        raw_tables={"specs": {"Display": "Vibrant panel", "Color": "Mica Silver"}},
        raw_sections={},
        price=52999.0,
    )
    result = pipeline.process_raw_product(raw)
    prov = result.provenance_record
    assert prov is not None
    assert prov["url"] == "https://example.com/laptop-prov-test"
    assert prov["summary"]["total_fields"] >= 35

    # 1. Populated CPU: resolved at L3
    cpu_model_prov = prov["field_provenance"]["cpu.model"]
    assert cpu_model_prov["status"] == "populated"
    assert cpu_model_prov["resolved_at"] == "L3_CPU_Anchor"
    assert "cpu_specs:" in cpu_model_prov["source"]

    # 2. Populated RAM: resolved at L4
    ram_prov = prov["field_provenance"]["memory.capacity_gb"]
    assert ram_prov["status"] == "populated"
    assert ram_prov["resolved_at"] == "L4_Deterministic"

    # 3. Rejected display: diagnosed as GATE_2_REJECTED
    disp_prov = prov["field_provenance"]["display.size_inches"]
    assert disp_prov["status"] == "unpopulated"
    assert disp_prov["reason"] == "GATE_2_REJECTED"
    assert "32.0" in disp_prov["details"]

    # 4. Enveloped battery spec returned None from AI: diagnosed as AI_UNRESOLVED
    battery_prov = prov["field_provenance"]["power_battery.battery_capacity_wh"]
    assert battery_prov["status"] == "unpopulated"
    assert battery_prov["reason"] == "AI_UNRESOLVED"

    # 5. Completely missing dimensions: diagnosed as NOT_PRESENT_IN_SOURCE
    width_prov = prov["field_provenance"]["physical.width_mm"]
    assert width_prov["status"] == "unpopulated"
    assert width_prov["reason"] == "NOT_PRESENT_IN_SOURCE"


# =============================================================================
# 9. Semantic Hardware Fields Tests (Dimensions, Ports, Audio, Webcam, Security)
# =============================================================================
def test_deterministic_extraction_semantic_fields():
    """Verify deterministic extraction of dimensions, ports, audio, webcam, and security."""
    extractor = DeterministicExtractor()
    title = "Lenovo LOQ 15IRX9 Gaming Laptop - Core i7-13645HX - RTX 4050"
    table = {
        "Dimensions (WxDxH)": "359.86 x 258.7 x 21.9-23.9 mm (14.17 x 10.19 x 0.86-0.94 inches)",
        "Case Color": "Luna Grey (with White Backlit Keyboard)",
        "Standard Ports": "1x Slim tip; 3x USB-A (USB 5Gbps); 1x USB-C (USB 10Gbps, PD 65-100W, DisplayPort 1.4); 1x HDMI 2.1; 1x RJ-45",
        "Ethernet": "100/1000M (RJ-45)",
        "Camera": "HD 720p with E-shutter",
        "Microphone": "2x, Array",
        "Speakers": "Stereo speakers, 2W x2, optimized with Nahimic Audio",
        "Keyboard": "White Backlit, English (UK)",
        "Fingerprint Reader": "No Fingerprint Reader",
        "Touchpad": "Buttonless Mylar surface multi-touch touchpad, 75 x 120 mm",
        "Security Chip": "Firmware TPM 2.0 Enabled",
    }

    specs, envelopes = extractor.extract(
        title=title,
        sanitized_table=table,
        sanitized_sections={},
    )

    # 1. Dimensions: parsed and normalized (W >= D >= H)
    assert specs["physical"]["width_mm"] == 359.9
    assert specs["physical"]["depth_mm"] == 258.7
    assert specs["physical"]["height_mm"] == 21.9
    assert specs["identity"]["color"] == "Luna Grey"

    # 2. Connectivity: ports & ethernet
    ports = specs["connectivity"]["ports"]
    assert len(ports) == 5
    assert any("USB-C" in p for p in ports)
    assert any("USB-A" in p for p in ports)
    assert any("HDMI" in p for p in ports)
    assert specs["connectivity"]["ethernet"] == "100/1000M (RJ-45)"

    # 3. Audio & Webcam
    assert specs["audio_webcam"]["webcam_resolution"] == "720p"
    assert "2x, Array" in specs["audio_webcam"]["microphone"]
    assert specs["audio_webcam"]["speaker_count"] == 2

    # 4. Build & Security
    assert specs["build_security"]["has_backlit_keyboard"] is True
    assert specs["build_security"]["has_fingerprint"] is False  # Negation handled correctly!
    assert "Buttonless Mylar" in specs["build_security"]["pointing_device"]
    assert "Firmware TPM 2.0 Enabled" in specs["build_security"]["security_features"]


def test_dimensions_centimeter_conversion():
    """Verify that cm dimensions are properly converted to metric mm."""
    extractor = DeterministicExtractor()
    title = "HP Victus 16 Gaming Laptop"
    table = {
        "Dimensions (W x D x H)": "36.9 x 25.94 x 2.29 cm",
    }
    specs, _ = extractor.extract(title=title, sanitized_table=table, sanitized_sections={})
    assert specs["physical"]["width_mm"] == 369.0
    assert specs["physical"]["depth_mm"] == 259.4
    assert specs["physical"]["height_mm"] == 22.9



