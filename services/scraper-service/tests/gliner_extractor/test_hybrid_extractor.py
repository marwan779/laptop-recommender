from unittest.mock import MagicMock
import pytest

from gliner_extractor.hybrid_extractor import HybridLaptopExtractor
from gliner_extractor.schema import empty_structured


def test_hybrid_extractor_crash_resilience():
    extractor = HybridLaptopExtractor()
    # Mock compumarts_extractor to raise an exception
    extractor.compumarts_extractor.extract = MagicMock(side_effect=RuntimeError("Simulated crash"))
    
    # Must not raise exception
    structured, meta = extractor.extract("Title", {"Key": "Val"}, store="compumarts")
    assert structured["extraction_meta"]["status"] == "failed"
    assert any("Simulated crash" in w for w in structured["extraction_meta"]["warnings"])
    assert "identity" in structured


def test_hybrid_extractor_metadata_forwarding():
    extractor = HybridLaptopExtractor()
    extractor.compumarts_extractor.extract = MagicMock(return_value=(empty_structured(), []))
    
    metadata = {
        "mpn": "83DV00PTED",
        "brand": "Lenovo",
        "price": 45000,
        "in_stock": True,
    }
    structured, _ = extractor.extract("Lenovo LOQ", {}, metadata=metadata, store="compumarts")
    
    assert structured["identity"]["manufacturer_part_number"] == "83DV00PTED"
    assert structured["identity"]["brand"] == "Lenovo"
    assert structured["price_egp"] == 45000.0
    assert structured["in_stock"] is True
    assert structured["extraction_meta"]["field_sources"]["identity.manufacturer_part_number"] == "metadata"


def test_hybrid_extractor_gliner_validation_gating():
    extractor = HybridLaptopExtractor()
    # Mock Tier 1 to return empty struct with an envelope
    struct = empty_structured()
    from gliner_extractor.compumarts_extractor import ContextEnvelope
    envelope = ContextEnvelope(
        target_area="cpu",
        target_labels=["cpu core count", "processor model"],
        raw_key="Processor",
        raw_value="Custom CPU with 999 cores and Model ABC",
        product_title="Test Laptop",
        sibling_context={},
        reason="test",
    )
    extractor.compumarts_extractor.extract = MagicMock(return_value=(struct, [envelope]))
    
    # Mock GLiNER output: 999 cores (invalid) and Model ABC (valid)
    extractor.gliner.extract_entities = MagicMock(return_value=[
        {"label": "cpu core count", "text": "999"},
        {"label": "processor model", "text": "Core Ultra 7 155H"},
    ])
    
    structured, _ = extractor.extract("Test Laptop", {}, store="compumarts")
    
    # 999 cores must be rejected!
    assert structured["cpu"]["cores"] is None
    assert any(r.get("field") == "cpu.cores" for r in structured["extraction_meta"]["rejected"])
    
    # Valid model must be accepted
    assert structured["cpu"]["model"] == "Core Ultra 7 155H"
    assert structured["extraction_meta"]["field_sources"]["cpu.model"] == "tier2"


def test_hybrid_extractor_status_determination():
    extractor = HybridLaptopExtractor()
    # Full laptop specs mock
    struct = empty_structured()
    struct["identity"]["brand"] = "Acer"
    struct["cpu"]["model"] = "i7-13700H"
    struct["memory"]["capacity_gb"] = 16
    struct["storage"]["capacity_gb"] = 512
    extractor.compumarts_extractor.extract = MagicMock(return_value=(struct, []))
    
    structured, _ = extractor.extract("Acer Nitro 5", {}, store="compumarts")
    assert structured["extraction_meta"]["status"] == "ok"
