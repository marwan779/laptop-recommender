"""Catalog and Laptop Details API Routes.

Provides endpoints for browsing and fetching authoritative laptop configurations,
35+ structured hardware specifications, live store offers with URLs, 11 TOPSIS
hardware scores, 5 community aspect scores, and bilingual review intelligence.
All database access is delegated to application services and repositories.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cursor import InvalidCursorError
from app.core.database import get_db
from app.schemas.laptop import (
    CatalogListResponse,
    FullLaptopDetailResponse,
    LaptopPriceHistoryResponse,
)
from app.services.catalog_query_service import CatalogQueryService

router = APIRouter(tags=["Catalog & Laptop Details"])


@router.get(
    "/laptops",
    response_model=CatalogListResponse,
    status_code=status.HTTP_200_OK,
    summary="Browse the paginated laptop catalog",
    description=(
        "Returns compact catalog cards with pricing, key hardware specs, and community review "
        "intelligence (community NLP score, evidence count, and bilingual pros/cons). "
        "Supports price range, brand, stock, and 0-100 metric gate filters. "
        "Uses deterministic composite keyset (cursor) pagination ordered by "
        "(min_price_egp, id); pass page_info.end_cursor with direction=next, or "
        "page_info.start_cursor with direction=prev. Includes 0-100 metric gates."
    ),
)
@router.get(
    "/catalog/laptops",
    response_model=CatalogListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_laptops(
    search: str | None = Query(default=None, description="Universal keyword search (model, name, MPN, SKU, title)."),
    min_price: float | None = Query(default=None, ge=0, description="Minimum price in EGP."),
    max_price: float | None = Query(default=None, ge=0, description="Maximum price in EGP."),
    brand: str | None = Query(default=None, description="Case-insensitive brand filter."),
    in_stock_only: bool = Query(default=True, description="Only return in-stock laptops."),
    cursor: str | None = Query(
        default=None,
        description="Opaque keyset pagination cursor from page_info.start_cursor/end_cursor.",
    ),
    direction: str = Query(
        default="next",
        pattern="^(next|prev)$",
        description="Pagination direction: 'next' or 'prev'.",
    ),
    limit: int = Query(default=12, ge=1, le=100, description="Page size (1-100)."),
    min_acoustics_score: float | None = Query(
        default=None, ge=0, le=100, description="Minimum real-world acoustics/fan-noise score."
    ),
    min_thermals_score: float | None = Query(
        default=None, ge=0, le=100, description="Minimum real-world thermals/cooling score."
    ),
    min_battery_score: float | None = Query(
        default=None, ge=0, le=100, description="Minimum real-world battery/reliability score."
    ),
    min_build_score: float | None = Query(
        default=None, ge=0, le=100, description="Minimum chassis build/hinge durability score."
    ),
    min_keyboard_score: float | None = Query(
        default=None, ge=0, le=100, description="Minimum keyboard/trackpad score."
    ),
    min_cpu_score: float | None = Query(
        default=None, ge=0, le=100, description="Minimum hardware CPU benchmark score."
    ),
    min_gpu_score: float | None = Query(
        default=None, ge=0, le=100, description="Minimum hardware GPU benchmark score."
    ),
    min_display_score: float | None = Query(
        default=None, ge=0, le=100, description="Minimum display quality/color score."
    ),
    min_value_score: float | None = Query(
        default=None, ge=0, le=100, description="Minimum value-for-money score."
    ),
    db: AsyncSession = Depends(get_db),
) -> CatalogListResponse:
    """Browse the catalog with filtering, universal search, and cursor pagination."""
    service = CatalogQueryService(session=db)
    try:
        return await service.list_laptops(
            search=search,
            min_price=min_price,
            max_price=max_price,
            brand=brand,
            in_stock_only=in_stock_only,
            cursor=cursor,
            direction=direction,
            limit=limit,
            min_acoustics_score=min_acoustics_score,
            min_thermals_score=min_thermals_score,
            min_battery_score=min_battery_score,
            min_build_score=min_build_score,
            min_keyboard_score=min_keyboard_score,
            min_cpu_score=min_cpu_score,
            min_gpu_score=min_gpu_score,
            min_display_score=min_display_score,
            min_value_score=min_value_score,
        )
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/laptops/{laptop_id}",
    response_model=FullLaptopDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get complete laptop specifications, offers, and hardware scores",
    description=(
        "Retrieve comprehensive 35+ hardware dimensions, all live store offers with direct "
        "product URLs, 11 normalized TOPSIS hardware and review metrics, the 5 community aspect "
        "scores (thermals, acoustics, build/hinges, keyboard/trackpad, real battery/reliability), "
        "and bilingual pros_ar/en and cons_ar/en. Accepts a database UUID, canonical_id "
        "(e.g. 'laptop_msi_prestige_9s713q222261'), or manufacturer part number (MPN)."
    ),
)
async def get_laptop_detail(
    laptop_id: str,
    db: AsyncSession = Depends(get_db),
) -> FullLaptopDetailResponse:
    """Retrieve full laptop detail payload for frontend product pages."""
    service = CatalogQueryService(session=db)
    return await service.get_laptop_detail(laptop_id)


@router.get(
    "/catalog/laptops/{laptop_id}",
    response_model=FullLaptopDetailResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_catalog_laptop_detail(
    laptop_id: str,
    db: AsyncSession = Depends(get_db),
) -> FullLaptopDetailResponse:
    """Alias for /laptops/{laptop_id}."""
    return await get_laptop_detail(laptop_id, db)


@router.get(
    "/laptops/{laptop_id}/price-history",
    response_model=LaptopPriceHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get multi-store price history telemetry over time",
    description=(
        "Returns one piecewise-constant price step series per active store offer, each extended "
        "to its latest verification timestamp, plus per-store and cross-store extrema and price "
        "deltas. History rows are appended only on real price or stock changes. Accepts a database "
        "UUID, canonical_id, or MPN. Use days to clip the window (e.g. 30, 90); omit for all-time."
    ),
)
async def get_laptop_price_history(
    laptop_id: str,
    days: int | None = Query(
        default=None,
        ge=1,
        le=3650,
        description="History window in days. Omit for all-time history.",
    ),
    db: AsyncSession = Depends(get_db),
) -> LaptopPriceHistoryResponse:
    """Return multi-store price curves for one canonical laptop."""
    service = CatalogQueryService(session=db)
    return await service.get_laptop_price_history(laptop_id, days=days)


@router.get(
    "/catalog/laptops/{laptop_id}/price-history",
    response_model=LaptopPriceHistoryResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_catalog_laptop_price_history(
    laptop_id: str,
    days: int | None = Query(default=None, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
) -> LaptopPriceHistoryResponse:
    """Alias for /laptops/{laptop_id}/price-history."""
    return await get_laptop_price_history(laptop_id, days, db)
