"""Tests for the Generic OCR Fallback Subsystem.

Verifies store-agnostic flyer image detection, RapidOCR text recognition, spatial line sorting,
URL guards, and end-to-end integration into PatternEngine and GenericCatalogPipeline.
"""

from __future__ import annotations

from io import BytesIO
import pytest
from PIL import Image, ImageDraw, ImageFont
from bs4 import BeautifulSoup
from unittest.mock import patch

from app.pipeline.ocr.engine import GenericOCRExtractor
from app.core.patterns.engine import PatternEngine
from app.pipeline.catalog_pipeline import GenericCatalogPipeline
from app.schemas.laptop import RetailerProduct


def _get_test_font() -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    candidates = [
        "arial.ttf",
        "DejaVuSans.ttf",
        "LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for font_name in candidates:
        try:
            return ImageFont.truetype(font_name, 28)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=28)
    except TypeError:
        return ImageFont.load_default()


@pytest.fixture(scope="module")
def synthetic_spec_flyer_bytes() -> bytes:
    """Generate an in-memory specification sheet PNG for deterministic OCR testing."""
    img = Image.new("RGB", (1000, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _get_test_font()

    spec_lines = [
        "HARDWARE SPECIFICATIONS",
        "Processor: Intel Core i9-13900H",
        "Graphics: NVIDIA GeForce RTX 4070 8GB",
        "Memory: 32GB DDR5 5200MHz",
        "Storage: 1TB NVMe PCIe 4.0 SSD",
        "Display: 16.0 inch WQXGA 240Hz IPS",
        "Battery: 90Wh 4-cell Li-ion",
        "Operating System: Windows 11 Home",
    ]

    y = 40
    for line in spec_lines:
        draw.text((40, y), line, fill=(0, 0, 0), font=font)
        y += 60

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_ocr_url_validation_guards():
    """Verify URL filtering accepts legitimate flyers and rejects badges, logos, and icons."""
    assert GenericOCRExtractor.is_valid_flyer_url("https://example.com/catalog/spec_sheet_lenovo.png") is True
    assert GenericOCRExtractor.is_valid_flyer_url("https://example.com/uploads/brochure.webp") is True
    assert GenericOCRExtractor.is_valid_flyer_url("https://example.com/flyer.jpg") is True

    # Blacklisted keywords
    assert GenericOCRExtractor.is_valid_flyer_url("https://example.com/brand_logo.png") is False
    assert GenericOCRExtractor.is_valid_flyer_url("https://example.com/rating_star.jpg") is False
    assert GenericOCRExtractor.is_valid_flyer_url("https://example.com/payment_badge.png") is False
    assert GenericOCRExtractor.is_valid_flyer_url("https://example.com/cart_icon.png") is False
    assert GenericOCRExtractor.is_valid_flyer_url("https://example.com/user_avatar.webp") is False

    # Invalid extension
    assert GenericOCRExtractor.is_valid_flyer_url("https://example.com/specs.pdf") is False
    assert GenericOCRExtractor.is_valid_flyer_url("https://example.com/specs.html") is False
    assert GenericOCRExtractor.is_valid_flyer_url("") is False


def test_ocr_image_dimension_guard():
    """Verify small images (< 350x250) are rejected to prevent running OCR on icons or thumbnails."""
    tiny_img = Image.new("RGB", (200, 150), color=(255, 255, 255))
    buf = BytesIO()
    tiny_img.save(buf, format="PNG")

    lines, conf = GenericOCRExtractor.extract_lines_from_bytes(buf.getvalue())
    assert lines == []
    assert conf == 0.0


def test_ocr_extraction_on_synthetic_flyer(synthetic_spec_flyer_bytes: bytes):
    """Verify RapidOCR extracts specification lines with high confidence from a spec image."""
    lines, conf = GenericOCRExtractor.extract_lines_from_bytes(synthetic_spec_flyer_bytes, min_confidence=0.60)

    assert len(lines) >= 5, f"Expected at least 5 lines, got {len(lines)}: {lines}"
    assert conf >= 0.70, f"Expected average confidence >= 0.70, got {conf}"

    full_text = " ".join(lines).lower()
    assert "intel" in full_text
    assert "core" in full_text
    assert "rtx 4070" in full_text
    assert "32gb" in full_text
    assert "1tb" in full_text


def test_ocr_network_failure_resilience():
    """Verify network failures or timeouts degrade gracefully without raising exceptions."""
    with patch("httpx.Client.get", side_effect=Exception("Connection refused")):
        lines, conf = GenericOCRExtractor.extract_lines_from_url("https://example.com/flyer.png")
        assert lines == []
        assert conf == 0.0


def test_pattern_engine_integration_with_ocr(synthetic_spec_flyer_bytes: bytes):
    """Verify PatternEngine detects flyer image and extracts specifications via OCR when DOM has no text."""
    html_without_text = """
    <div id="product-content">
        <div id="tab-description">
            <img src="https://elbadrgroupeg.store/image/catalog/flyers/legion-specs.png" alt="Legion Spec Sheet">
        </div>
    </div>
    """
    soup = BeautifulSoup(html_without_text, "html.parser")
    title = "Lenovo Legion Pro 5 16IRX8 Gaming Laptop"

    with patch.object(GenericOCRExtractor, "fetch_image_bytes", return_value=synthetic_spec_flyer_bytes):
        res = PatternEngine.extract_specs(
            soup=soup,
            title=title,
            store_key="elbadr",
            base_url="https://elbadrgroupeg.store",
        )

        assert res.has_specs_image is True
        assert res.specs_image_url == "https://elbadrgroupeg.store/image/catalog/flyers/legion-specs.png"
        assert res.specs_extraction_source == "ocr", f"Expected source 'ocr', got '{res.specs_extraction_source}'"
        assert res.ocr_confidence is not None and res.ocr_confidence >= 0.70
        assert res.ocr_line_count is not None and res.ocr_line_count >= 5
        assert len(res.specs) >= 5, f"Expected >= 5 extracted specs, got {len(res.specs)}: {res.specs}"


def test_ocr_to_catalog_pipeline_end_to_end(synthetic_spec_flyer_bytes: bytes):
    """Verify end-to-end extraction through GenericCatalogPipeline using OCR-extracted specs."""
    html = """
    <div class="product-description">
        <img src="https://compumarts.com/cdn/shop/files/spec-flyer-rtx4070.jpg">
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    title = "ASUS ROG Strix G16 G614JI Gaming Laptop"

    with patch.object(GenericOCRExtractor, "fetch_image_bytes", return_value=synthetic_spec_flyer_bytes):
        spec_res = PatternEngine.extract_specs(
            soup=soup,
            title=title,
            store_key="compumarts",
            base_url="https://www.compumarts.com",
        )

    assert spec_res.specs_extraction_source == "ocr"

    product = RetailerProduct(
        store_name="CompuMarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title=title,
        product_url="https://www.compumarts.com/products/asus-rog-strix-g16",
        retailer_product_id="ASUS-ROG-G16",
        price_egp=85000.0,
        price_str="85,000 EGP",
        in_stock=True,
        specs=spec_res.specs,
        raw_description=spec_res.raw_description,
        specs_image_url=spec_res.specs_image_url,
    )

    pipeline = GenericCatalogPipeline(no_audit=True)
    res = pipeline.process_single(product, store_key="compumarts")

    assert res is not None, "Product was unexpectedly rejected by pipeline validation"
    specs = res.get("specs", {})

    # Verify CPU extraction from OCR
    assert specs["cpu"]["manufacturer"] == "Intel"
    assert "13900H" in specs["cpu"]["model"]

    # Verify GPU extraction from OCR
    assert "RTX 4070" in specs["gpu"]["model"]
    assert specs["gpu"]["vram_gb"] == 8

    # Verify Memory extraction from OCR
    assert specs["memory"]["capacity_gb"] == 32
    assert specs["memory"]["memory_type"] == "DDR5"

    # Verify Storage extraction from OCR
    assert specs["storage"]["capacity_gb"] == 1024
    assert specs["storage"]["storage_type"] == "SSD"
