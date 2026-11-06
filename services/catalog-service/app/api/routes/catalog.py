"""Catalog and Laptop Details API Routes.

Provides endpoints for fetching authoritative laptop configurations, 35+ structured
hardware specifications, store-specific live offers with URLs, and 11 TOPSIS hardware scores.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.laptop import FullLaptopDetailResponse
from app.services.catalog_query_service import CatalogQueryService

router = APIRouter(tags=["Catalog & Laptop Details"])


@router.get(
    "/laptops/{laptop_id}",
    response_model=FullLaptopDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get complete laptop specifications, offers, and hardware scores",
    description=(
        "Retrieve comprehensive 35+ hardware dimensions, all live store offers "
        "with direct product URLs, and 11 normalized TOPSIS metrics for a laptop. "
        "Accepts database UUID, canonical_id (e.g. 'laptop_msi_prestige_9s713q222261'), "
        "or manufacturer part number (MPN)."
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
