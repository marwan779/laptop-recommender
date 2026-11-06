"""FastAPI presentation router for TOPSIS laptop recommendations."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.post(
    "",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate personalized multi-criteria laptop recommendations",
    description=(
        "Executes dynamic in-memory TOPSIS ranking across all candidate laptops meeting budget "
        "and persona gates. Supports bilingual Arabic/English text prompts to extract implicit "
        "hardware constraints and apply criteria weight boosts. Returns explainable badges and store price breakdown."
    ),
)
@router.post(
    "/recommend",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def generate_recommendations(
    request: RecommendationRequest,
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    """Generate persona-weighted TOPSIS recommendations."""
    service = RecommendationService(session=db)
    return await service.get_recommendations(request)
