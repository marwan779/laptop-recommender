"""Application service for building social share HTML and OpenGraph card images."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.logger import get_logger
from app.domain.share import (
    ShareCardData,
    build_share_html,
    build_share_metadata,
    render_og_card_png,
)
from app.schemas.laptop import FullLaptopDetailResponse
from app.services.catalog_query_service import CatalogQueryService

logger = get_logger("catalog.share_service")


def _to_share_card_data(detail: FullLaptopDetailResponse) -> ShareCardData:
    brand = detail.brand or ""
    family = detail.laptop_family or ""
    model = detail.laptop_model or ""
    parts = [p for p in [brand, family, model] if p and p.lower() not in model.lower()] if model else [brand, family]
    display_name = " ".join(parts).strip() or detail.title
    if model and model.lower() not in display_name.lower():
        display_name = f"{display_name} {model}".strip()

    cpu_line = (detail.cpu.line or "").strip() if detail.cpu else ""
    cpu_model = (detail.cpu.model or "").strip() if detail.cpu else ""
    if cpu_line and cpu_model and cpu_line.lower() in cpu_model.lower():
        cpu_label = cpu_model
    else:
        cpu_label = f"{cpu_line} {cpu_model}".strip()
    gpu_label = detail.gpu.model if detail.gpu and detail.gpu.model else ""
    if detail.gpu and detail.gpu.vram_gb and detail.gpu.vram_gb > 0 and f"{detail.gpu.vram_gb}gb" not in gpu_label.lower():
        gpu_label = f"{gpu_label} {detail.gpu.vram_gb}GB".strip()

    ram_label = f"{detail.memory.capacity_gb}GB {detail.memory.memory_type}".strip() if detail.memory and detail.memory.capacity_gb else ""
    storage_gb = detail.storage.capacity_gb if detail.storage else 0
    storage_label = (
        f"{storage_gb // 1024}TB SSD"
        if storage_gb >= 1024 and storage_gb % 1024 == 0
        else (f"{storage_gb}GB SSD" if storage_gb else "")
    )
    disp_parts = []
    if detail.display and detail.display.size_inches:
        disp_parts.append(f'{detail.display.size_inches:.1f}"')
    if detail.display and detail.display.refresh_rate_hz and detail.display.refresh_rate_hz >= 90:
        disp_parts.append(f"{detail.display.refresh_rate_hz}Hz")
    if detail.display and detail.display.panel_type:
        disp_parts.append(detail.display.panel_type)
    display_label = " ".join(disp_parts)

    community_score = (
        float(detail.metrics.community_nlp_score)
        if detail.metrics and detail.metrics.community_nlp_score is not None
        else None
    )

    return ShareCardData(
        canonical_id=detail.canonical_id,
        brand=brand,
        display_name=display_name,
        title=detail.title,
        min_price_egp=float(detail.min_price_egp or 0),
        max_price_egp=float(detail.max_price_egp) if detail.max_price_egp is not None else None,
        cheapest_store=detail.cheapest_store or "Egypt",
        stores_count=int(detail.stores_count or 1),
        cpu_label=cpu_label,
        gpu_label=gpu_label,
        ram_label=ram_label,
        storage_label=storage_label,
        display_label=display_label,
        community_score=community_score,
        reviews_count=int(detail.reviews_evidence_count or 0),
        mpn=detail.mpn,
    )


class ShareService:
    """Coordinates catalog detail loading, thumbnail fetching, and OG card generation."""

    def __init__(self, session: AsyncSession) -> None:
        self._catalog = CatalogQueryService(session=session)

    async def get_share_html(self, laptop_id: str, lang: str, base_url: str) -> str:
        detail = await self._catalog.get_laptop_detail(laptop_id)
        data = _to_share_card_data(detail)
        meta = build_share_metadata(data, lang=lang, base_url=base_url)
        return build_share_html(meta, lang=lang)

    async def get_og_image(self, laptop_id: str, image_format: str = "JPEG") -> bytes:
        detail = await self._catalog.get_laptop_detail(laptop_id)
        data = _to_share_card_data(detail)
        thumb_bytes: bytes | None = None
        if detail.thumbnail_url and detail.thumbnail_url.startswith(("http://", "https://")):
            try:
                async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
                    resp = await client.get(detail.thumbnail_url)
                    if resp.status_code == 200 and len(resp.content) < 5 * 1024 * 1024:
                        thumb_bytes = resp.content
            except Exception as exc:
                logger.debug("Thumbnail fetch failed for %s: %s", laptop_id, exc)
        return render_og_card_png(data, thumbnail_bytes=thumb_bytes, image_format=image_format)
