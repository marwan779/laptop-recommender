"""FastAPI presentation router for TOPSIS laptop recommendations."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.post(
    "",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate personalized 10-criteria TOPSIS laptop recommendations",
    description=(
        "Executes dynamic in-memory TOPSIS ranking across all candidate laptops meeting budget "
        "and persona gates using 10 criteria: 9 benefit criteria (including the real-world "
        "`community_nlp_score`) and 1 cost criterion (`effective_price_egp`). "
        "Dual-Impact free-text prompts are processed through ChromaDB bilingual pro/con cosine "
        "similarity, which adjusts per-laptop review scores, while bilingual intent keywords boost "
        "the relevant TOPSIS criteria weights. Returns bilingual pros/cons, review evidence counts, "
        "the 5 community aspect scores, explainable badges, and store price breakdowns. "
        "The `status` field is `OK`, `GATES_RELAXED_FOR_LOW_BUDGET`, or "
        "`BUDGET_TOO_LOW_FOR_CATEGORY` (the latter returns the 3 cheapest active alternatives)."
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
    http_request: Request,
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    """Generate persona-weighted TOPSIS recommendations."""
    chroma_service = getattr(http_request.app.state, "chroma_reviews", None)
    service = RecommendationService(session=db, chroma_service=chroma_service)
    return await service.get_recommendations(request)
