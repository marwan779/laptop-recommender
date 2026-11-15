"""Pydantic request schemas for the HTTP presentation layer."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.infrastructure.chroma_repository import CHROMA_DEFAULT_DIR


class RecommendRequest(BaseModel):
    max_budget_egp: float = Field(default=300000.0, gt=0)
    min_budget_egp: Optional[float] = Field(default=None, ge=0)
    persona: str = Field(default="balanced")
    user_text_prompt: Optional[str] = None
    min_ram_gb: Optional[int] = Field(default=None, ge=1)
    min_storage_gb: Optional[int] = Field(default=None, ge=1)
    require_dgpu: Optional[bool] = None
    brand_filter: Optional[List[str]] = None
    custom_weights: Optional[Dict[str, float]] = None
    top_k: int = Field(default=10, ge=1, le=50)
    include_workloads: bool = True
    candidate_laptops: Optional[List[Dict[str, Any]]] = None


class IngestReviewsRequest(BaseModel):
    reviews_path: str = "reviews_deduplicated_v6.json"
    catalog_path: str = "unified_catalog_topsis_ready_v6.json"
    chroma_dir: str = CHROMA_DEFAULT_DIR
    recalibrate_first: bool = True
    raw_reviews_payload: Optional[Dict[str, Any]] = None
    include_profiles: bool = True
    enrich_raw: bool = True
    force_reenrich: bool = False
    enricher_mode: str = "primary_with_fallback"
