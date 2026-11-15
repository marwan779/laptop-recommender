#!/usr/bin/env python3
"""
Raw Reviews Enricher (Format A -> Enriched Format B1)
====================================================
Thin facade over the clean-architecture implementation:

- `app.domain.enrichment`      : pure chunking, scoring, prompts, validation.
- `app.infrastructure`         : Jina-v3, SovereignEG HTTP, delta cache adapters.
- `app.services`               : dependency-injected enrichment orchestration.

All public symbols below keep their original names and signatures.
"""

from __future__ import annotations

import argparse
import json

from app.domain.enrichment.chunking import (
    _clean_text,
    _format_catalog_specs_summary,
    _gather_raw_candidate_chunks,
    _is_noisy_or_offtopic,
    _select_top_candidates_for_jina,
    _split_clean_chunks,
    compute_chassis_delta_hash,
    count_missing_profiles,
    detect_reviews_format,
)
from app.domain.enrichment.models import (
    ASPECT_KEYS,
    DEFAULT_DELTA_CACHE_PATH,
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_PRIMARY_MODEL,
    ENRICHER_SCHEMA_VERSION,
    ENRICHMENT_JSON_SCHEMA,
    SOVEREIGNEG_PRICING_EGP_PER_1M,
    _ARABIC_CHAR_RE,
    _ASPECT_FALLBACK_AR,
    _ASPECT_FALLBACK_EN,
    _ASPECT_KEYWORDS,
    _CODE_BLOCK_RE,
    _CON_ANCHORS,
    _DESKTOP_PART_RE,
    _DETAILS_BLOCK_RE,
    _HTML_TAG_RE,
    _HW_UNIT_RE,
    _LAPTOP_CONTEXT_RE,
    _NOISE_ANCHOR,
    _NOISE_PATTERNS,
    _PRO_ANCHORS,
    _THINK_TAG_RE,
    _URL_RE,
)
from app.domain.enrichment.scoring import (
    _build_llm_messages,
    _build_synthesized_texts,
    _compute_zero_llm_aspect_scores,
    _estimate_egp_cost,
    _extract_json_from_llm_content,
    _finalize_profile_with_recalibration,
    _merge_unique_bullets,
    _score_snippets_from_vectors,
    is_valid_nlp_profile,
    validate_enriched_profile,
)
from app.infrastructure.delta_cache_repository import _load_json_dict, _save_json_atomic
from app.infrastructure.jina_embedder import (
    _get_anchor_embeddings,
    _get_jina_embed_fn,
    _score_and_select_evidence_for_item,
    extract_hardware_sentences_jina,
    extract_hardware_sentences_jina_batch,
)
from app.infrastructure.sovereigneg_client import (
    SCRIPT_DIR,
    _call_sovereigneg_model,
    load_enricher_env,
)
from app.services.reviews_enrichment_service import (
    enrich_chassis_with_fallback,
    enrich_chassis_zero_llm,
    enrich_reviews_dataset,
)

load_enricher_env()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich Format A raw chassis reviews into Format B1.")
    parser.add_argument("--input", default="cleaned_and_enriched_chassis_reviews_v6.json")
    parser.add_argument("--output", default="cleaned_and_enriched_chassis_reviews_v6.json")
    parser.add_argument("--catalog", default="unified_catalog_topsis_ready_v6.json")
    parser.add_argument("--cache", default=DEFAULT_DELTA_CACHE_PATH)
    parser.add_argument("--mode", default="primary_with_fallback", choices=["primary_with_fallback", "single_model", "zero_llm"])
    parser.add_argument("--primary-model", default=None)
    parser.add_argument("--fallback-model", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    _, summary = enrich_reviews_dataset(
        payload_or_path=args.input,
        catalog_path=args.catalog,
        delta_cache_path=args.cache,
        primary_model=args.primary_model,
        fallback_model=args.fallback_model,
        mode=args.mode,
        force=args.force,
        max_workers=args.workers,
        output_path=args.output,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
