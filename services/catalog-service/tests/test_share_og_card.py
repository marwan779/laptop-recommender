"""Unit tests for pure domain OpenGraph metadata and PNG card rendering."""

import io

from PIL import Image

from app.domain.share import (
    ShareCardData,
    build_share_html,
    build_share_metadata,
    render_og_card_png,
)


def _sample_card() -> ShareCardData:
    return ShareCardData(
        canonical_id="laptop_asus_tuf_gaming_fx607vurl167w",
        brand="ASUS",
        display_name="ASUS TUF Gaming F16 FX607VU-RL167W",
        title="ASUS TUF Gaming F16 FX607VU-RL167W",
        min_price_egp=69999.0,
        max_price_egp=73500.0,
        cheapest_store="2B Egypt",
        stores_count=3,
        cpu_label="Core 7 240H",
        gpu_label="RTX 4050 6GB",
        ram_label="16GB DDR5",
        storage_label="512GB SSD",
        display_label='16.0" 144Hz IPS',
        community_score=74.0,
        reviews_count=29,
        mpn="FX607VURL167W",
    )


def test_build_share_metadata_and_html_bilingual():
    card = _sample_card()
    meta_en = build_share_metadata(card, lang="en", base_url="https://example.com")
    assert "69,999 EGP" in meta_en["title"]
    assert "Save 3,501 EGP" in meta_en["description"]
    assert meta_en["image_url"] == "https://example.com/share/laptop_asus_tuf_gaming_fx607vurl167w/og-image.jpg"
    assert meta_en["redirect_url"] == "https://example.com/?laptop=laptop_asus_tuf_gaming_fx607vurl167w&lang=en"

    html_ar = build_share_html(
        build_share_metadata(card, lang="ar", base_url="https://example.com"),
        lang="ar",
    )
    assert 'property="og:image"' in html_ar
    assert 'property="og:image:width" content="1200"' in html_ar
    assert 'name="twitter:card" content="summary_large_image"' in html_ar
    assert 'dir="rtl"' in html_ar


def test_render_og_card_png_dimensions():
    card = _sample_card()
    # Create a tiny synthetic PNG thumbnail to verify image compositing too
    thumb_buf = io.BytesIO()
    Image.new("RGB", (320, 240), (200, 200, 200)).save(thumb_buf, format="PNG")

    png_bytes = render_og_card_png(card, thumbnail_bytes=thumb_buf.getvalue())
    img = Image.open(io.BytesIO(png_bytes))
    assert img.format == "PNG"
    assert img.size == (1200, 630)
