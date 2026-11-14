# Laptop Recommender & Workload AI Microservice — Backend & DevOps Integration Guide

## 1. Architecture & Memory Sizing
- **Embeddings Model:** `jinaai/jina-embeddings-v3` (`float32` on CPU, `truncate_dim=512` Matryoshka, `max_seq_length=256`).
- **Vector Store:** Persistent ChromaDB (`./chroma_reviews_db`, collection `laptop_chassis_reviews_jina_v3`, cosine space, 360 unique `pro`/`con` chassis documents).
- **Ranking Engine:** 10-column Vector TOPSIS (`cpu_score`, `gpu_score`, `power_therm_score`, `display_score`, `mobility_score`, `longevity_score`, `ergonomics_score`, `connectivity_score`, `community_nlp_score`, and `effective_price_egp` cost) + LRU Query Cache (max 256 entries) + Deterministic Role-Model Workload & Career Track Evaluator (`workload_engine.py`).
- **Runtime Memory Footprint (DevOps Sizing):**
  - Measured singleton process RSS RAM: **~3.18 GB** (`3,176.9 MB` verified in benchmark).
  - Recommended Kubernetes / Docker container memory limit: **`4Gi–4.5Gi`**.
  - **IMPORTANT:** Always launch with `--workers 1` (`uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 1`) so workers do not duplicate the `jinaai/jina-embeddings-v3` model in RAM. Blocking inference and DB operations execute inside `asyncio.to_thread` to keep the ASGI event loop responsive.

---

## 2. API Endpoints & Exact JSON Payloads

### `GET /health`
Returns model readiness, indexed ChromaDB count, LRU cache statistics, and current process RSS RAM.

**Example Response (`200 OK`):**
```json
{
  "status": "ok",
  "model_name": "jinaai/jina-embeddings-v3",
  "embedding_dim": 512,
  "model_loaded": true,
  "chroma_collection_name": "laptop_chassis_reviews_jina_v3",
  "chroma_document_count": 360,
  "catalog_laptops_count": 295,
  "lru_cache_info": {
    "hits": 4,
    "misses": 2,
    "maxsize": 256,
    "currsize": 2
  },
  "process_ram_mb": 3180.4
}
```

---

### `POST /recommend`
Ranks in-stock laptops within budget using persona gates (including `min_vram_gb >= 6` for `ai_and_game_dev`), dynamic Egyptian Arabic + English ChromaDB review boosting, 10-column TOPSIS, and per-laptop workload evaluations.

**Request Payload:**
```json
{
  "max_budget_egp": 75000,
  "min_budget_egp": null,
  "persona": "ai_and_game_dev",
  "user_text_prompt": "عايز لاب تبريده قوي للذكاء الاصطناعي والبرمجة ومفصلاته متينة",
  "min_ram_gb": 16,
  "min_storage_gb": null,
  "require_dgpu": null,
  "brand_filter": null,
  "custom_weights": null,
  "top_k": 5,
  "include_workloads": true,
  "candidate_laptops": null
}
```
> **Note for Backend:** Omit `candidate_laptops` (or pass `null`) to score against the service's in-memory 295-laptop catalog (`unified_catalog_topsis_ready_v6.json`), or pass a pre-filtered array of catalog laptop objects synced from PostgreSQL.
> Supported `persona` keys: `"gaming"`, `"ai_and_game_dev"`, `"programming"`, `"content_creation"`, `"student_and_office"`, `"business_and_mobility"`, `"balanced"`.

**Response Payload (`200 OK`):**
```json
{
  "status": "OK",
  "message_ar": "تم ترتيب أفضل اللابتوبات المطابقة لاحتياجاتك بنجاح.",
  "persona": "ai_and_game_dev",
  "persona_label_ar": "الذكاء الاصطناعي وتطوير الألعاب والـ 3D",
  "persona_label_en": "AI / ML, Game Dev & 3D Rendering",
  "gates_relaxed_for_low_budget": false,
  "total_candidates_before_floor": 42,
  "total_candidates_after_gates_and_floor": 18,
  "applied_budget_window_egp": [45000.0, 75000.0],
  "effective_weights": {
    "cpu_score": 0.1456,
    "gpu_score": 0.2039,
    "power_therm_score": 0.1893,
    "display_score": 0.0728,
    "mobility_score": 0.0218,
    "longevity_score": 0.0728,
    "ergonomics_score": 0.0218,
    "connectivity_score": 0.0291,
    "community_nlp_score": 0.1602,
    "effective_price_egp": 0.0827
  },
  "chroma_nlp_metadata": {
    "adjusted_count": 48,
    "semantic_weight_boosts": {
      "power_therm_score": 0.056
    }
  },
  "execution_time_ms": 11.4,
  "closest_alternatives": [],
  "results": [
    {
      "rank": 1,
      "canonical_id": "laptop_...",
      "brand": "Lenovo",
      "laptop_family": "LOQ",
      "laptop_model": "...",
      "title": "...",
      "thumbnail_url": "https://...",
      "topsis_match_score": 78.42,
      "effective_price_egp": 64999.0,
      "cheapest_store": "elbadr",
      "available_stores": ["elbadr", "sigma"],
      "prices_by_store": {"elbadr": 64999.0, "sigma": 67500.0},
      "why_recommended_ar": ["..."],
      "why_recommended_en": ["..."],
      "topsis_inputs": {"cpu_score": 82.1, "community_nlp_score": 84.5, "...": "..."},
      "community_reviews": {
        "community_nlp_score": 84.5,
        "aspect_scores": {"thermals_score": 85.0, "...": "..."},
        "pros_ar": ["..."],
        "cons_ar": ["..."],
        "pros_en": ["..."],
        "cons_en": ["..."]
      },
      "workloads": {
        "hardware_context": {"cpu_architecture": "x86_64", "vram_gb": 8, "has_cuda": true},
        "games_1080p": [{"name": "Cyberpunk 2077", "estimated_fps": 78, "tier": "Medium-High 50-79 FPS", "screen_bottleneck": false}],
        "software_benchmarks": [{"name": "DaVinci Resolve", "readiness_score": 81.2, "display_color_warning": false}],
        "career_tracks": [{"track": "AI / ML & Data Science", "suitability": "Recommended (Local CUDA Training Ready)", "local_training_ready": true}]
      }
    }
  ]
}
```
If no laptops match the budget + category, `status` returns `"BUDGET_TOO_LOW_FOR_CATEGORY"` with `closest_alternatives` containing the 3 lowest-priced active laptops.

---

### `POST /ingest-reviews`
Cron job webhook to recalibrate 5-aspect chassis scores, rebuild the ChromaDB `512d` index, refresh in-memory state, and clear the LRU cache.

**Request Payload:**
```json
{
  "reviews_path": "cleaned_and_enriched_chassis_reviews_v6.json",
  "catalog_path": "unified_catalog_topsis_ready_v6.json",
  "chroma_dir": "./chroma_reviews_db",
  "recalibrate_first": true,
  "raw_reviews_payload": null,
  "include_profiles": true
}
```

**Response Payload (`200 OK`):**
```json
{
  "status": "ok",
  "indexed_documents_count": 360,
  "updated_laptops_count": 295,
  "chroma_collection_name": "laptop_chassis_reviews_jina_v3",
  "profiles_by_canonical_id": {
    "laptop_...": {
      "community_nlp_score": 82.72,
      "aspect_scores": {"thermals_score": 84.0, "...": "..."},
      "pros_ar": ["..."],
      "cons_ar": ["..."]
    }
  }
}
```
