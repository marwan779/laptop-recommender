# Laptop Recommender & Workload AI Microservice — Backend & DevOps Integration Guide

## 1. Architecture & Memory Sizing
- **Embeddings Model:** `jinaai/jina-embeddings-v3` (`float32` on CPU, `truncate_dim=512` Matryoshka, `max_seq_length=256`).
- **Vector Store:** Persistent ChromaDB (`./chroma_reviews_db`, collection `laptop_chassis_reviews_jina_v3`, cosine space, unique `pro`/`con` chassis documents).
- **Ranking Engine (Clean Architecture — `app.domain.recommendation.topsis` & `app.domain.metrics.scoring`):**
  - **14-Column Vector TOPSIS** across **13 benefit criteria** (`cpu_score`, `gpu_compute_score`, `vram_score`, `power_therm_score`, `display_gaming_score`, `display_creator_score`, `battery_score`, `portability_score`, `upgradeability_score`, `build_quality_score`, `ergonomics_score`, `connectivity_score`, `community_nlp_score`) plus **`effective_price_egp` cost**.
  - **Backward Compatibility:** `topsis_inputs` continues computing and returning the legacy aggregated columns (`gpu_score`, `display_score`, `mobility_score`, `longevity_score`) alongside the 8 split metrics.
  - **Unreviewed Baseline Default:** `community_nlp_score` defaults to **`56.0`** (`DEFAULT_COMMUNITY_NLP_SCORE`) when a laptop has no matched reviews yet.
  - **16 Personas + 5 Legacy Aliases:** Supports 16 specialized personas (`gaming`, `gaming_esports`, `gaming_aaa`, `gaming_budget`, `creative`, `creative_video`, `creative_2d_photo`, `creative_3d_cad_gamedev`, `tech`, `tech_ai_ml`, `tech_web_mobile`, `tech_cyber_vms`, `balanced`, `daily_student`, `daily_business`, `daily_office`) and automatically resolves the 5 legacy keys (`ai_and_game_dev` -> `tech_ai_ml`, `programming` -> `tech_web_mobile`, `content_creation` -> `creative`, `student_and_office` -> `daily_student`, `business_and_mobility` -> `daily_business`).
  - **Calibrated Value-per-EGP (`calculate_calibrated_value_score`):** Smooth logistic-sigmoid calibration bounded strictly to **`[15.0, 97.5]`** (`midpoint=0.92`, `steepness=2.5`, fallback `50.0` when `price_egp < 10000` or `None`) prevents `100.0` score saturation and is applied to both catalog `value_score` and query-time `persona_value_score`.
  - **Caching & Workloads:** Shared LRU Query Cache (`maxsize=256`) + Deterministic Role-Model Workload & Career Track Evaluator (`app.domain.recommendation.workloads`).
- **Authentication (`APIKeyAuthMiddleware`):** `GET /health` is public; all `POST` endpoints (`/score-prompt`, `/recommend`, `/ingest-reviews`) enforce `X-API-Key` authentication when `REQUIRE_API_KEY=true`.
- **Runtime Memory Footprint (DevOps Sizing):**
  - Measured singleton process RSS RAM: **~3.18 GB** (`3,176.9 MB` verified in benchmark).
  - Recommended Kubernetes / Docker container memory limit: **`4Gi–4.5Gi`**.
  - **IMPORTANT:** Always launch with `--workers 1` (`uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --workers 1`) so workers do not duplicate the `jinaai/jina-embeddings-v3` model in RAM. Blocking inference and DB operations execute inside `asyncio.to_thread` to keep the ASGI event loop responsive.

---

## 2. API Endpoints & Exact JSON Payloads

### `GET /health`
Public endpoint returning model readiness, indexed ChromaDB count, LRU cache statistics, and current process RSS RAM.

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

### `POST /score-prompt`
Protected by `X-API-Key`. Lightweight NLP scoring endpoint that encodes `user_text_prompt` with `jinaai/jina-embeddings-v3`, executes the LRU-cached (`maxsize=256`) Dual-Vector ChromaDB search (`pro` vs `con`), computes a signal-spread `nlp_dynamic_weight` in `[0.10, 0.25]`, and extracts explicit numeric/feature `parsed_constraints` (omitting `semantic_weight_boosts` / `CRITERIA_SEMANTIC_ANCHORS`).

**Request Payload:**
```json
{
  "user_text_prompt": "رامات 32 وشاشة OLED"
}
```

**Response Payload (`200 OK`):**
```json
{
  "adjusted_nlp_scores": {
    "laptop_...": 86.12
  },
  "nlp_dynamic_weight": 0.2104,
  "parsed_constraints": {
    "min_ram_gb": 32,
    "require_oled": true
  },
  "execution_time_ms": 8.45
}
```

---

### `POST /recommend`
Protected by `X-API-Key`. Ranks in-stock laptops within budget using persona gates (including `min_vram_gb >= 6` and `require_nvidia` for `tech_ai_ml`), dynamic Egyptian Arabic + English ChromaDB review boosting (`nlp_dynamic_weight`), 14-column Vector TOPSIS, calibrated `persona_value_score` / `value_score`, and per-laptop workload evaluations.

**Request Payload:**
```json
{
  "max_budget_egp": 75000,
  "min_budget_egp": null,
  "persona": "tech_ai_ml",
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
> **Note for Backend:** Omit `candidate_laptops` (or pass `null`) to score against the service's in-memory catalog (`unified_catalog_topsis_ready_v6.json`), or pass a pre-filtered array of catalog laptop objects synced from PostgreSQL.
> Supported 16 `persona` keys: `"gaming"`, `"gaming_esports"`, `"gaming_aaa"`, `"gaming_budget"`, `"creative"`, `"creative_video"`, `"creative_2d_photo"`, `"creative_3d_cad_gamedev"`, `"tech"`, `"tech_ai_ml"`, `"tech_web_mobile"`, `"tech_cyber_vms"`, `"balanced"`, `"daily_student"`, `"daily_business"`, `"daily_office"`.
> Legacy aliases (automatically resolved): `"ai_and_game_dev"` (`-> "tech_ai_ml"`), `"programming"` (`-> "tech_web_mobile"`), `"content_creation"` (`-> "creative"`), `"student_and_office"` (`-> "daily_student"`), `"business_and_mobility"` (`-> "daily_business"`).

**Response Payload (`200 OK`):**
```json
{
  "status": "OK",
  "message_ar": "تم ترتيب أفضل اللابتوبات المطابقة لاحتياجاتك بنجاح.",
  "persona": "tech_ai_ml",
  "persona_label_ar": "الذكاء الاصطناعي وتعلم الآلة وعلم البيانات",
  "persona_label_en": "AI / ML Engineering & CUDA Compute",
  "gates_relaxed_for_low_budget": false,
  "total_candidates_before_floor": 42,
  "total_candidates_after_gates_and_floor": 18,
  "applied_budget_window_egp": [45000.0, 75000.0],
  "effective_weights": {
    "cpu_score": 0.145,
    "gpu_compute_score": 0.2175,
    "vram_score": 0.1631,
    "power_therm_score": 0.1414,
    "display_gaming_score": 0.0,
    "display_creator_score": 0.0091,
    "battery_score": 0.0091,
    "portability_score": 0.0091,
    "upgradeability_score": 0.0906,
    "build_quality_score": 0.0272,
    "ergonomics_score": 0.0181,
    "connectivity_score": 0.0362,
    "community_nlp_score": 0.043,
    "effective_price_egp": 0.0906
  },
  "chroma_nlp_metadata": {
    "adjusted_count": 48,
    "semantic_weight_boosts": {
      "power_therm_score": 0.056
    },
    "nlp_dynamic_weight": 0.1904
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
      "persona_value_score": 76.18,
      "value_score": 74.92,
      "effective_price_egp": 64999.0,
      "cheapest_store": "elbadr",
      "available_stores": ["elbadr", "sigma"],
      "prices_by_store": {"elbadr": 64999.0, "sigma": 67500.0},
      "why_recommended_ar": ["..."],
      "why_recommended_en": ["..."],
      "topsis_inputs": {"cpu_score": 82.1, "gpu_compute_score": 63.0, "vram_score": 74.0, "community_nlp_score": 84.5, "value_score": 74.92},
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
Protected by `X-API-Key`. Cron job webhook to recalibrate 5-aspect chassis scores, rebuild the ChromaDB `512d` index, refresh in-memory state, and clear the LRU cache.

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
