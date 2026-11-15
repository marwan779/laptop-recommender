#!/usr/bin/env python3
"""
Upgraded ChromaDB & Aspect Recalibration Engine (chroma_reviews_engine.py)
--------------------------------------------------------------------------
Thin facade over:
- `app.domain.reviews.calibration`   : pure aspect recalibration rules.
- `app.infrastructure.jina_embedder` : Jina-v3 singleton embedding adapter.
- `app.infrastructure.chroma_repository` : ChromaDB persistence/query adapter.
- `app.services.reviews_ingestion_service` : ingestion orchestration.

Works both as an importable Python module AND a CLI script for Backend Cron Jobs.
"""
import argparse

from app.domain.reviews.calibration import (
    _BASELINE_ASPECT_RE,
    _extract_baseline_aspects,
    _recalibrate_item,
)
from app.infrastructure.chroma_repository import (
    CHROMA_DEFAULT_DIR,
    COLLECTION_NAME,
    ChromaReviewsRepository,
)
from app.infrastructure.jina_embedder import (
    EMBED_DIM,
    MODEL_NAME,
    JinaV3EmbeddingFunction,
)
from app.services.reviews_ingestion_service import (
    build_chroma_reviews_db,
    ensure_deduplicated_reviews_file,
    recalibrate_catalog_and_reviews,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build/Update ChromaDB Review Index with Jina-v3")
    parser.add_argument("--reviews", default="reviews_deduplicated_v6.json")
    parser.add_argument("--catalog", default="unified_catalog_topsis_ready_v6.json")
    parser.add_argument("--chroma-dir", default=CHROMA_DEFAULT_DIR)
    parser.add_argument("--model", default=MODEL_NAME)
    args = parser.parse_args()

    build_chroma_reviews_db(
        reviews_json_path=args.reviews,
        catalog_json_path=args.catalog,
        chroma_dir=args.chroma_dir,
        model_name=args.model,
    )
