#!/usr/bin/env python3
"""
Production FastAPI Microservice Wrapper (api_server.py)
-------------------------------------------------------
Exposes the Laptop Recommendation & NLP ChromaDB Engine over HTTP:
  - GET  /health          : Model readiness, ChromaDB count, LRU cache stats, and RSS RAM (MB).
  - POST /recommend       : Budget-scoped 10-column TOPSIS + Dual-Vector ChromaDB + Workloads.
  - POST /ingest-reviews  : Backend Cron Job hook to recalibrate 5-aspects & refresh ChromaDB.

Run with single worker to share the ~3.2 GB in-memory `jinaai/jina-embeddings-v3` singleton:
    uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 1
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
import psutil
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from chroma_reviews_engine import (
    CHROMA_DEFAULT_DIR,
    COLLECTION_NAME,
    EMBED_DIM,
    MODEL_NAME,
    build_chroma_reviews_db,
)
from recommendation_pipeline import LaptopRecommenderService

os.environ.setdefault("HF_HUB_OFFLINE", "1")

_service: Optional[LaptopRecommenderService] = None


def _get_service() -> LaptopRecommenderService:
    global _service
    if _service is None:
        _service = LaptopRecommenderService()
    return _service


@asynccontextmanager
async def lifespan(app: FastAPI):
    _get_service()
    yield


app = FastAPI(
    title="Egyptian Laptop Recommender & Workload AI Microservice",
    version="1.0.0",
    description="10-column Vector TOPSIS + Jina-v3 (512d) Dual-Vector ChromaDB + Deterministic Workloads API.",
    lifespan=lifespan,
)


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


def health() -> Dict[str, Any]:
    svc = _get_service()
    proc = psutil.Process(os.getpid())
    ram_mb = round(proc.memory_info().rss / (1024.0 * 1024.0), 1)
    doc_count = svc.collection.count() if svc.collection is not None else 0
    cache_info = svc._cached_dual_query.cache_info()
    return {
        "status": "ok" if (svc.query_emb_fn is not None and svc.collection is not None) else "degraded",
        "model_name": MODEL_NAME,
        "embedding_dim": EMBED_DIM,
        "model_loaded": svc.query_emb_fn is not None,
        "chroma_collection_name": COLLECTION_NAME,
        "chroma_document_count": doc_count,
        "catalog_laptops_count": len(svc._cached_catalog or []),
        "lru_cache_info": {
            "hits": cache_info.hits,
            "misses": cache_info.misses,
            "maxsize": cache_info.maxsize,
            "currsize": cache_info.currsize,
        },
        "process_ram_mb": ram_mb,
    }


def recommend(
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
    candidate_laptops: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    svc = _get_service()
    return svc.recommend(
        laptops=candidate_laptops,
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


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    _get_service()
    return await asyncio.to_thread(health)


@app.post("/recommend")
async def recommend_laptops(req: RecommendRequest) -> Dict[str, Any]:
    _get_service()
    return await asyncio.to_thread(
        recommend,
        max_budget_egp=req.max_budget_egp,
        min_budget_egp=req.min_budget_egp,
        persona=req.persona,
        user_text_prompt=req.user_text_prompt,
        min_ram_gb=req.min_ram_gb,
        min_storage_gb=req.min_storage_gb,
        require_dgpu=req.require_dgpu,
        brand_filter=req.brand_filter,
        custom_weights=req.custom_weights,
        top_k=req.top_k,
        include_workloads=req.include_workloads,
        candidate_laptops=req.candidate_laptops,
    )


def _run_ingest_sync(req: IngestReviewsRequest) -> Dict[str, Any]:
    from raw_reviews_enricher import detect_reviews_format, enrich_reviews_dataset
    from audit_and_deduplicate_reviews import run_audit_and_dedup

    if req.raw_reviews_payload is not None:
        payload = req.raw_reviews_payload
    else:
        if not Path(req.reviews_path).exists():
            raise FileNotFoundError(f"Reviews file not found: {req.reviews_path}")
        with open(req.reviews_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

    detected_format = detect_reviews_format(payload)
    enrichment_summary: Optional[Dict[str, Any]] = None
    target_dedup_path = req.reviews_path

    if detected_format == "format_b2_deduplicated":
        if req.raw_reviews_payload is not None:
            Path(target_dedup_path).parent.mkdir(parents=True, exist_ok=True)
            with open(target_dedup_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
    else:
        src_p = Path(req.reviews_path)
        if req.raw_reviews_payload is None:
            target_dedup_path = str(src_p.with_suffix(".deduplicated.json"))

        b1_path = src_p.with_suffix(".enriched_b1.json")
        if (detected_format == "format_a_raw" or req.force_reenrich) and req.enrich_raw:
            _, enrichment_summary = enrich_reviews_dataset(
                payload_or_path=payload,
                catalog_path=req.catalog_path,
                mode=req.enricher_mode,
                force=req.force_reenrich,
                output_path=str(b1_path),
            )
            b1_input_path = str(b1_path)
        else:
            enrichment_summary = {
                "detected_format": detected_format,
                "total_chassis": len(payload.get("laptops", [])),
                "enriched_count": 0,
                "skipped_reason": (
                    "Already enriched Format B1"
                    if detected_format == "format_b1_enriched"
                    else "enrich_raw=False"
                ),
            }
            if req.raw_reviews_payload is not None:
                b1_path.parent.mkdir(parents=True, exist_ok=True)
                with open(b1_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                b1_input_path = str(b1_path)
            else:
                b1_input_path = req.reviews_path

        tasks_md_out = str(Path(target_dedup_path).with_name("youtube_gap_tasks.md"))
        run_audit_and_dedup(
            reviews_in=b1_input_path,
            catalog_in=req.catalog_path,
            dedup_out=target_dedup_path,
            tasks_md_out=tasks_md_out,
        )

    if not Path(target_dedup_path).exists():
        raise FileNotFoundError(f"Reviews file not found: {target_dedup_path}")

    summary = build_chroma_reviews_db(
        reviews_json_path=target_dedup_path,
        catalog_json_path=req.catalog_path,
        chroma_dir=req.chroma_dir,
        model_name=MODEL_NAME,
        recalibrate_first=req.recalibrate_first,
        auto_enrich=False,
    )

    # Refresh in-memory catalog, deduplicated reviews lookup, ChromaDB collection handle, and clear LRU query cache
    svc = _get_service()
    if Path(req.catalog_path).exists():
        with open(req.catalog_path, "r", encoding="utf-8") as f:
            svc._cached_catalog = json.load(f).get("laptops", [])
    svc._load_reviews_lookup(target_dedup_path)
    client = chromadb.PersistentClient(path=req.chroma_dir)
    svc.collection = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=svc.query_emb_fn,
    )
    svc._cached_dual_query.cache_clear()

    resp: Dict[str, Any] = {
        "status": "ok",
        "detected_format": detected_format,
        "enrichment_summary": enrichment_summary,
        "effective_reviews_path": target_dedup_path,
        "indexed_documents_count": summary["indexed_documents_count"],
        "updated_laptops_count": summary["updated_laptops_count"],
        "chroma_collection_name": COLLECTION_NAME,
    }
    if req.include_profiles:
        resp["profiles_by_canonical_id"] = summary["profiles_by_canonical_id"]
    return resp


@app.post("/ingest-reviews")
async def ingest_reviews(req: IngestReviewsRequest) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(_run_ingest_sync, req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
