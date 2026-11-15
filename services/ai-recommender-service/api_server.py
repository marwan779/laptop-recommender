#!/usr/bin/env python3
"""
Production FastAPI Microservice Wrapper (api_server.py)
-------------------------------------------------------
Thin facade over the presentation layer in `app.api`:
  - GET  /health          : Model readiness, ChromaDB count, LRU cache stats, and RSS RAM (MB).
  - POST /recommend       : Budget-scoped 10-column TOPSIS + Dual-Vector ChromaDB + Workloads.
  - POST /ingest-reviews  : Backend Cron Job hook to recalibrate 5-aspects & refresh ChromaDB.

Run with single worker to share the ~3.2 GB in-memory `jinaai/jina-embeddings-v3` singleton:
    uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 1
"""
from app.api.app import app, lifespan
from app.api.routes import (
    _get_service,
    _run_ingest_sync,
    health,
    recommend,
    router,
)
from app.api.schemas import IngestReviewsRequest, RecommendRequest
from app.infrastructure.chroma_repository import COLLECTION_NAME, CHROMA_DEFAULT_DIR
from app.infrastructure.jina_embedder import EMBED_DIM, MODEL_NAME
