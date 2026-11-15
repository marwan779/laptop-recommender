"""Application service wrapping the recommendation pipeline lifecycle."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from recommendation_pipeline import LaptopRecommenderService


class RecommendationService:
    """Thin application-service facade over `LaptopRecommenderService`."""

    def __init__(self, recommender: Optional[LaptopRecommenderService] = None) -> None:
        self._recommender = recommender

    @property
    def recommender(self) -> LaptopRecommenderService:
        if self._recommender is None:
            self._recommender = LaptopRecommenderService()
        return self._recommender

    def warm_up(self) -> LaptopRecommenderService:
        return self.recommender

    def refresh_reviews_state(
        self,
        chroma_dir: Optional[str] = None,
        reviews_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Refresh live Chroma collection and review lookup caches after batch ingestion."""
        if self._recommender is not None:
            self._recommender.refresh_reviews_state(
                chroma_dir=chroma_dir,
                reviews_payload=reviews_payload,
            )

    def recommend(
        self,
        laptops: Optional[List[Dict[str, Any]]] = None,
        max_budget_egp: float = 300000.0,
        min_budget_egp: Optional[float] = None,
        persona: str = "balanced",
        user_text_prompt: Optional[str] = None,
        min_ram_gb: Optional[int] = None,
        min_storage_gb: Optional[int] = None,
        require_dgpu: Optional[bool] = None,
        brand_filter: Optional[List[str]] = None,
        custom_weights: Optional[Dict[str, float]] = None,
        top_k: int = 10,
        include_workloads: bool = True,
    ) -> Dict[str, Any]:
        return self.recommender.recommend(
            laptops=laptops,
            max_budget_egp=max_budget_egp,
            min_budget_egp=min_budget_egp,
            persona=persona,
            user_text_prompt=user_text_prompt,
            min_ram_gb=min_ram_gb,
            min_storage_gb=min_storage_gb,
            require_dgpu=require_dgpu,
            brand_filter=brand_filter,
            custom_weights=custom_weights,
            top_k=top_k,
            include_workloads=include_workloads,
        )


_DEFAULT_SERVICE: Optional[RecommendationService] = None


def get_recommendation_service() -> RecommendationService:
    """FastAPI lifecycle singleton accessor."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = RecommendationService()
    return _DEFAULT_SERVICE
