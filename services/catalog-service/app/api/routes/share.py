"""Social Share OpenGraph HTML and Dynamic OG Image Routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.share_service import ShareService

router = APIRouter(tags=["Social Share"])


def _resolve_base_url(request: Request) -> str:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    if host.endswith((".ngrok-free.app", ".ngrok.app", ".trycloudflare.com")):
        proto = "https"
    return f"{proto}://{host}"


@router.get(
    "/share/{laptop_id}",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    summary="OpenGraph share landing page for social crawlers and deep links",
)
async def share_laptop_page(
    laptop_id: str,
    request: Request,
    lang: str = Query(default="ar", pattern="^(ar|en)$"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    service = ShareService(session=db)
    html_body = await service.get_share_html(
        laptop_id=laptop_id,
        lang=lang,
        base_url=_resolve_base_url(request),
    )
    return HTMLResponse(
        content=html_body,
        headers={"Cache-Control": "public, max-age=600"},
    )


@router.get(
    "/share/{laptop_id}/og-image.jpg",
    status_code=status.HTTP_200_OK,
    summary="Render a 1200x630 OpenGraph JPEG preview card for a laptop",
)
async def share_laptop_og_image_jpg(
    laptop_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ShareService(session=db)
    img_bytes = await service.get_og_image(laptop_id=laptop_id, image_format="JPEG")
    return Response(
        content=img_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Length": str(len(img_bytes)),
        },
    )


@router.get(
    "/share/{laptop_id}/og-image.png",
    status_code=status.HTTP_200_OK,
    summary="Render a 1200x630 OpenGraph PNG preview card for a laptop",
)
async def share_laptop_og_image_png(
    laptop_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ShareService(session=db)
    img_bytes = await service.get_og_image(laptop_id=laptop_id, image_format="PNG")
    return Response(
        content=img_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Length": str(len(img_bytes)),
        },
    )
