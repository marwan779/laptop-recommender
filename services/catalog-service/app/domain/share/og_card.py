"""Pure domain logic for social-media OpenGraph metadata and 1200x630 PNG card rendering."""

from __future__ import annotations

import html
import io
import os
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

# "The Verified Instrument" palette
BG_APP = (10, 14, 19)
BG_SURFACE = (16, 22, 29)
BG_RAISED = (21, 29, 39)
BG_INPUT = (13, 19, 26)
STUDIO_WELL = (237, 235, 230)
BORDER_SUBTLE = (30, 40, 54)
BORDER_STRONG = (43, 57, 76)
TEXT_PRIMARY = (241, 245, 249)
TEXT_SECONDARY = (155, 168, 184)
TEXT_MUTED = (114, 128, 146)
GOLD = (233, 185, 73)
GOLD_BRIGHT = (245, 201, 92)
GOLD_DIM = (48, 39, 19)
CYAN = (34, 211, 238)
EMERALD = (52, 211, 153)
EMERALD_DIM = (16, 48, 38)

_BOLD_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)
_REG_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


@dataclass(frozen=True)
class ShareCardData:
    canonical_id: str
    brand: str
    display_name: str
    title: str
    min_price_egp: float
    max_price_egp: float | None
    cheapest_store: str
    stores_count: int
    cpu_label: str
    gpu_label: str
    ram_label: str
    storage_label: str
    display_label: str
    community_score: float | None = None
    reviews_count: int = 0
    mpn: str | None = None


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _BOLD_FONT_PATHS if bold else _REG_FONT_PATHS
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    max_lines: int = 2,
) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines:
        lines.append(current)
    elif len(words) > 1:
        # Ellipsize last line if overflowed
        last = lines[-1]
        while last and draw.textbbox((0, 0), f"{last}...", font=font)[2] > max_width:
            last = last[:-1].rstrip()
        lines[-1] = f"{last}..."
    return lines


def _truncate_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> str:
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    trimmed = text
    while trimmed and draw.textbbox((0, 0), f"{trimmed}...", font=font)[2] > max_width:
        trimmed = trimmed[:-1].rstrip()
    return f"{trimmed}..." if trimmed else text


def build_share_metadata(data: ShareCardData, lang: str, base_url: str) -> dict[str, str]:
    is_ar = lang == "ar"
    clean_base = base_url.rstrip("/")
    price_str = f"{round(data.min_price_egp):,}"
    savings = (
        round(data.max_price_egp - data.min_price_egp)
        if data.max_price_egp and data.max_price_egp > data.min_price_egp
        else 0
    )

    specs_parts = [p for p in [data.cpu_label, data.gpu_label, data.ram_label, data.storage_label, data.display_label] if p]
    specs_line = " · ".join(specs_parts[:4])

    if is_ar:
        title = f"{data.display_name} — {price_str} ج.م في {data.cheapest_store}"
        savings_note = f" (وفّر {savings:,} ج.م)" if savings >= 200 else ""
        review_note = (
            f" · تقييم المراجعات {data.community_score:.0f}/100"
            if data.community_score is not None and data.reviews_count > 0
            else ""
        )
        description = f"{specs_line}{savings_note}{review_note} — قارن الأسعار والمواصفات في مصر."
        site_name = "دليل اللابتوب — مصر"
    else:
        title = f"{data.display_name} — {price_str} EGP at {data.cheapest_store}"
        savings_note = f" (Save {savings:,} EGP)" if savings >= 200 else ""
        review_note = (
            f" · Review score {data.community_score:.0f}/100"
            if data.community_score is not None and data.reviews_count > 0
            else ""
        )
        description = f"{specs_line}{savings_note}{review_note} — Compare live prices & verified specs in Egypt."
        site_name = "Laptop Guide Egypt"

    share_url = f"{clean_base}/share/{data.canonical_id}?lang={'ar' if is_ar else 'en'}"
    image_url = f"{clean_base}/share/{data.canonical_id}/og-image.jpg"
    redirect_url = f"{clean_base}/?laptop={data.canonical_id}&lang={'ar' if is_ar else 'en'}"

    return {
        "title": title,
        "description": description,
        "site_name": site_name,
        "share_url": share_url,
        "image_url": image_url,
        "redirect_url": redirect_url,
        "locale": "ar_EG" if is_ar else "en_US",
    }


def build_share_html(meta: dict[str, str], lang: str) -> str:
    title = html.escape(meta["title"], quote=True)
    description = html.escape(meta["description"], quote=True)
    site_name = html.escape(meta["site_name"], quote=True)
    share_url = html.escape(meta["share_url"], quote=True)
    image_url = html.escape(meta["image_url"], quote=True)
    redirect_url = html.escape(meta["redirect_url"], quote=True)
    locale = html.escape(meta["locale"], quote=True)
    html_lang = "ar" if lang == "ar" else "en"
    html_dir = "rtl" if lang == "ar" else "ltr"

    return f"""<!doctype html>
<html lang="{html_lang}" dir="{html_dir}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <meta name="description" content="{description}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="{site_name}" />
  <meta property="og:locale" content="{locale}" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{share_url}" />
  <meta name="image" property="og:image" content="{image_url}" />
  <meta property="og:image:secure_url" content="{image_url}" />
  <meta property="og:image:type" content="image/jpeg" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  <meta property="og:image:alt" content="{title}" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{title}" />
  <meta name="twitter:description" content="{description}" />
  <meta name="twitter:image" content="{image_url}" />
  <link rel="canonical" href="{redirect_url}" />
</head>
<body style="background:#0A0E13;color:#F1F5F9;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;">
  <p><a href="{redirect_url}" style="color:#F5C95C;">{title}</a></p>
  <script>window.location.replace({meta["redirect_url"]!r});</script>
</body>
</html>
"""


def render_og_card_png(data: ShareCardData, thumbnail_bytes: bytes | None = None, image_format: str = "PNG") -> bytes:
    width, height = 1200, 630
    img = Image.new("RGB", (width, height), BG_APP)
    draw = ImageDraw.Draw(img)

    # Outer card container
    draw.rounded_rectangle((28, 28, width - 28, height - 28), radius=24, fill=BG_SURFACE, outline=BORDER_STRONG, width=2)

    font_tag = _load_font(16, bold=True)
    font_title = _load_font(34, bold=True)
    font_price = _load_font(50, bold=True)
    font_sub = _load_font(20, bold=False)
    font_sub_bold = _load_font(20, bold=True)
    font_pill = _load_font(18, bold=True)
    font_foot = _load_font(17, bold=False)

    # Top header strip
    brand_text = data.brand.upper()
    draw.rounded_rectangle((60, 56, 60 + max(110, len(brand_text) * 14 + 32), 92), radius=8, fill=BG_RAISED, outline=BORDER_SUBTLE, width=1)
    draw.text((76, 65), brand_text, font=font_tag, fill=TEXT_PRIMARY)

    # Live verified badge on top-right
    badge_w = 290
    badge_x0 = width - 60 - badge_w
    draw.rounded_rectangle((badge_x0, 56, width - 60, 92), radius=18, fill=EMERALD_DIM, outline=EMERALD, width=1)
    draw.ellipse((badge_x0 + 16, 70, badge_x0 + 24, 78), fill=EMERALD)
    draw.text((badge_x0 + 34, 65), "VERIFIED LIVE · EGYPT", font=font_tag, fill=EMERALD)

    # Left column: Studio Lightbox Well (4:3 product photo)
    well_box = (60, 122, 470, 462)
    draw.rounded_rectangle(well_box, radius=16, fill=STUDIO_WELL)

    pasted = False
    if thumbnail_bytes:
        try:
            thumb = Image.open(io.BytesIO(thumbnail_bytes)).convert("RGBA")
            pad = 24
            max_w = (well_box[2] - well_box[0]) - pad * 2
            max_h = (well_box[3] - well_box[1]) - pad * 2
            thumb.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            tx = well_box[0] + (well_box[2] - well_box[0] - thumb.width) // 2
            ty = well_box[1] + (well_box[3] - well_box[1] - thumb.height) // 2
            img.paste(thumb, (tx, ty), thumb)
            pasted = True
        except Exception:
            pasted = False

    if not pasted:
        fallback_font = _load_font(44, bold=True)
        label = data.brand.upper()[:6]
        bbox = draw.textbbox((0, 0), label, font=fallback_font)
        tx = well_box[0] + (well_box[2] - well_box[0] - (bbox[2] - bbox[0])) // 2
        ty = well_box[1] + (well_box[3] - well_box[1] - (bbox[3] - bbox[1])) // 2
        draw.text((tx, ty), label, font=fallback_font, fill=(60, 72, 88))

    # Right column: Title, Price, Specs
    rx = 504
    max_rw = width - 60 - rx
    title_lines = _wrap_text(draw, data.display_name, font_title, max_rw, max_lines=2)
    ty = 120
    for line in title_lines:
        draw.text((rx, ty), line, font=font_title, fill=TEXT_PRIMARY)
        ty += 44

    # Price box
    price_top = ty + 14
    draw.rounded_rectangle((rx, price_top, width - 60, price_top + 130), radius=14, fill=BG_INPUT, outline=BORDER_SUBTLE, width=1)
    price_str = f"{round(data.min_price_egp):,} EGP"
    draw.text((rx + 22, price_top + 16), price_str, font=font_price, fill=GOLD_BRIGHT)
    store_line = _truncate_text(draw, f"Lowest at {data.cheapest_store}", font_sub_bold, max_rw - 44)
    draw.text((rx + 22, price_top + 84), store_line, font=font_sub_bold, fill=TEXT_SECONDARY)

    # Savings pill inside price box (right aligned) if multi-store spread >= 200
    savings = (
        round(data.max_price_egp - data.min_price_egp)
        if data.max_price_egp and data.max_price_egp > data.min_price_egp
        else 0
    )
    if savings >= 200 and data.stores_count >= 2:
        sav_text = f"Save {savings:,} EGP"
        sbbox = draw.textbbox((0, 0), sav_text, font=font_pill)
        sw = (sbbox[2] - sbbox[0]) + 28
        sx0 = width - 82 - sw
        draw.rounded_rectangle((sx0, price_top + 24, width - 82, price_top + 60), radius=18, fill=EMERALD_DIM, outline=EMERALD, width=1)
        draw.text((sx0 + 14, price_top + 31), sav_text, font=font_pill, fill=EMERALD)

    # Spec pills (2x2 grid)
    spec_items = [
        ("CPU", data.cpu_label),
        ("GPU", data.gpu_label),
        ("MEM", f"{data.ram_label} · {data.storage_label}".strip(" ·")),
        ("DSP", data.display_label),
    ]
    pill_top = price_top + 148
    pill_w = (max_rw - 14) // 2
    pill_h = 54
    for idx, (tag, val) in enumerate(spec_items):
        col = idx % 2
        row = idx // 2
        px0 = rx + col * (pill_w + 14)
        py0 = pill_top + row * (pill_h + 12)
        draw.rounded_rectangle((px0, py0, px0 + pill_w, py0 + pill_h), radius=10, fill=BG_RAISED, outline=BORDER_SUBTLE, width=1)
        draw.ellipse((px0 + 14, py0 + 23, px0 + 22, py0 + 31), fill=CYAN)
        clean_val = _truncate_text(draw, val or "N/A", font_pill, pill_w - 42)
        draw.text((px0 + 32, py0 + 17), clean_val, font=font_pill, fill=TEXT_PRIMARY)

    # Bottom footer strip
    draw.line((60, height - 92, width - 60, height - 92), fill=BORDER_SUBTLE, width=1)
    if data.community_score is not None and data.reviews_count > 0:
        rev_text = f"Review Score: {data.community_score:.0f}/100 ({data.reviews_count} real reviews)"
    else:
        rev_text = f"Compare {data.stores_count} Egyptian store{'s' if data.stores_count != 1 else ''} live"
    draw.text((60, height - 68), rev_text, font=font_foot, fill=TEXT_SECONDARY)

    if data.mpn:
        mpn_text = f"MPN: {data.mpn}"
        mbbox = draw.textbbox((0, 0), mpn_text, font=font_foot)
        draw.text((width - 60 - (mbbox[2] - mbbox[0]), height - 68), mpn_text, font=font_foot, fill=TEXT_MUTED)

    buf = io.BytesIO()
    fmt = image_format.upper()
    if fmt == "JPEG":
        img.save(buf, format="JPEG", quality=90, optimize=True, progressive=True)
    else:
        img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
