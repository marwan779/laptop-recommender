"""Application service coordinating review-file ingestion into catalog + ChromaDB."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.domain.enrichment.chunking import detect_reviews_format
from app.domain.reviews.calibration import _extract_baseline_aspects, _recalibrate_item
from app.infrastructure.chroma_repository import (
    CHROMA_DEFAULT_DIR,
    ChromaReviewsRepository,
)
from app.infrastructure.jina_embedder import MODEL_NAME
from app.services.reviews_enrichment_service import enrich_reviews_dataset


class ReviewsIngestionService:
    """Coordinates dedupe, enrichment, recalibration and vector-store rebuild."""

    def __init__(
        self,
        enricher: Any = None,
        vector_store: Optional[ChromaReviewsRepository] = None,
    ) -> None:
        self._enrich_reviews_dataset = enricher or enrich_reviews_dataset
        self.vector_store = vector_store or ChromaReviewsRepository()

    def ensure_deduplicated_reviews_file(
        self,
        reviews_path: str,
        catalog_path: str = "unified_catalog_topsis_ready_v6.json",
        auto_enrich: bool = True,
        force_reenrich: bool = False,
        enricher_mode: str = "primary_with_fallback",
    ) -> tuple[str, str, Optional[Dict[str, Any]]]:
        """
        Auto-detect Format A (`laptops[]` raw) vs. Format B1 (`laptops[]` enriched) vs.
        Format B2 (`chassis_reviews[]` deduplicated). When given Format A or B1, enrich
        (if needed) and deduplicate into a sibling `.deduplicated.json` Format B2 file.
        """
        with open(reviews_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        from audit_and_deduplicate_reviews import run_audit_and_dedup

        fmt = detect_reviews_format(payload)
        if fmt == "format_b2_deduplicated":
            return reviews_path, fmt, None

        src_path = Path(reviews_path)
        enrichment_summary: Optional[Dict[str, Any]] = None
        b1_input_path = reviews_path

        if (fmt == "format_a_raw" or force_reenrich) and auto_enrich:
            b1_path = src_path.with_suffix(".enriched_b1.json")
            _, enrichment_summary = self._enrich_reviews_dataset(
                payload_or_path=payload,
                catalog_path=catalog_path,
                mode=enricher_mode,
                force=force_reenrich,
                output_path=str(b1_path),
            )
            b1_input_path = str(b1_path)
        elif fmt == "format_b1_enriched":
            enrichment_summary = {
                "detected_format": fmt,
                "total_chassis": len(payload.get("laptops", [])),
                "enriched_count": 0,
                "skipped_reason": "Already enriched Format B1",
            }

        b2_path = src_path.with_suffix(".deduplicated.json")
        tasks_md = src_path.with_name(f"{src_path.stem}_gap_tasks.md")
        run_audit_and_dedup(
            reviews_in=b1_input_path,
            catalog_in=catalog_path,
            dedup_out=str(b2_path),
            tasks_md_out=str(tasks_md),
        )
        return str(b2_path), fmt, enrichment_summary

    def recalibrate_catalog_and_reviews(
        self,
        reviews_path: str = "reviews_deduplicated_v6.json",
        catalog_path: str = "unified_catalog_topsis_ready_v6.json",
        auto_enrich: bool = True,
        force_reenrich: bool = False,
        enricher_mode: str = "primary_with_fallback",
    ) -> Dict[str, Any]:
        """
        Fixes Bayesian clustering in the 5 Field Review Aspects with a balanced 1.25x contrast multiplier
        (preventing 96.0/42.0 saturation) anchored to original baseline aspect scores, and updates
        `reviews_deduplicated_v6.json`, `unified_catalog_topsis_ready_v6.json`, and cleaned JSON if present.
        Auto-detects Format A raw vs. Format B1 enriched payloads before recalibrating.
        """
        if Path(reviews_path).exists():
            reviews_path, _, _ = self.ensure_deduplicated_reviews_file(
                reviews_path=reviews_path,
                catalog_path=catalog_path,
                auto_enrich=auto_enrich,
                force_reenrich=force_reenrich,
                enricher_mode=enricher_mode,
            )
        with open(reviews_path, "r", encoding="utf-8") as f:
            rev_data = json.load(f)

        cat_data = None
        cat_map: Dict[str, Any] = {}
        if Path(catalog_path).exists():
            with open(catalog_path, "r", encoding="utf-8") as f:
                cat_data = json.load(f)
            cat_map = {l["canonical_id"]: l for l in cat_data.get("laptops", [])}

        # Load baseline aspects by chassis_key from cleaned JSON if available so recalibration is idempotent
        cleaned_path = Path("cleaned_and_enriched_chassis_reviews_v6.json")
        baseline_by_ckey: Dict[str, Dict[str, float]] = {}
        legacy_prof_by_ckey: Dict[str, Dict[str, Any]] = {}
        if cleaned_path.exists():
            with open(cleaned_path, "r", encoding="utf-8") as f:
                cleaned_data = json.load(f)
            for it in cleaned_data.get("laptops", []):
                ck = it.get("chassis_key")
                prof = it.get("nlp_review_profile", {})
                if ck and prof:
                    baseline_by_ckey[ck] = _extract_baseline_aspects(prof, prof.get("aspect_scores", {}))
                    legacy_prof_by_ckey[ck] = prof

        prof_by_cid: Dict[str, Dict[str, Any]] = {}

        if "chassis_reviews" in rev_data:
            for item in rev_data.get("chassis_reviews", []):
                ck = item["chassis_key"]
                cids = item.get("matched_canonical_ids", [])
                base_asp = baseline_by_ckey.get(ck) or item.get("aspect_scores") or {}
                item_specs = item.get("specs") if isinstance(item.get("specs"), dict) else None
                if base_asp:
                    recal = _recalibrate_item(
                        item.get("identity", {}),
                        cids,
                        cids[0] if cids else None,
                        base_asp,
                        cat_map,
                        item_specs=item_specs,
                    )
                else:
                    recal = {
                        "community_nlp_score": 75.0,
                        "aspect_scores": {
                            "thermals_score": 75.0,
                            "acoustics_score": 75.0,
                            "build_and_hinges_score": 75.0,
                            "keyboard_and_trackpad_score": 75.0,
                            "real_battery_and_reliability_score": 75.0,
                        },
                    }
                item["community_nlp_score"] = recal["community_nlp_score"]
                item["aspect_scores"] = recal["aspect_scores"]

                clean_lists = item.get("clean_profile_lists", {})
                ed_pros = [c["text"] for c in item.get("deduplicated_chunks", []) if c.get("source_type") == "scraped_editorial" and c.get("polarity") == "pro"]
                ed_cons = [c["text"] for c in item.get("deduplicated_chunks", []) if c.get("source_type") == "scraped_editorial" and c.get("polarity") == "con"]
                base_prof = dict(legacy_prof_by_ckey.get(ck, {}))
                base_prof.update({
                    "community_nlp_score": recal["community_nlp_score"],
                    "aspect_scores": recal["aspect_scores"],
                    "pros_ar": list(clean_lists.get("pros_ar", base_prof.get("pros_ar", []))),
                    "cons_ar": list(clean_lists.get("cons_ar", base_prof.get("cons_ar", []))),
                    "pros_en": list(dict.fromkeys(list(clean_lists.get("pros_en", base_prof.get("pros_en", []))) + ed_pros)),
                    "cons_en": list(dict.fromkeys(list(clean_lists.get("cons_en", base_prof.get("cons_en", []))) + ed_cons)),
                })
                for mcid in cids:
                    prof_by_cid[mcid] = base_prof
        else:
            for item in rev_data.get("laptops", []):
                prof = item.get("nlp_review_profile", {})
                aspects = prof.get("aspect_scores", {})
                if not aspects:
                    continue
                cids = item.get("matched_canonical_ids", [])
                base_asp = _extract_baseline_aspects(prof, aspects)
                item_specs = item.get("specs") if isinstance(item.get("specs"), dict) else None
                recal = _recalibrate_item(
                    item.get("identity", {}),
                    cids,
                    item.get("primary_canonical_id"),
                    base_asp,
                    cat_map,
                    item_specs=item_specs,
                )
                prof["community_nlp_score"] = recal["community_nlp_score"]
                prof["aspect_scores"] = recal["aspect_scores"]
                for mcid in cids:
                    prof_by_cid[mcid] = prof

        with open(reviews_path, "w", encoding="utf-8") as f:
            json.dump(rev_data, f, indent=2, ensure_ascii=False)

        if cat_data:
            for lap in cat_data.get("laptops", []):
                cid = lap["canonical_id"]
                if cid in prof_by_cid:
                    p = prof_by_cid[cid]
                    lap["derived_metrics"]["topsis_inputs"]["community_nlp_score"] = p["community_nlp_score"]
                    lap["derived_metrics"]["community_reviews"] = p
            with open(catalog_path, "w", encoding="utf-8") as f:
                json.dump(cat_data, f, indent=2, ensure_ascii=False)

        return rev_data

    def build_chroma_reviews_db(
        self,
        reviews_json_path: str = "reviews_deduplicated_v6.json",
        catalog_json_path: str = "unified_catalog_topsis_ready_v6.json",
        chroma_dir: str = CHROMA_DEFAULT_DIR,
        model_name: str = MODEL_NAME,
        recalibrate_first: bool = True,
        auto_enrich: bool = True,
        force_reenrich: bool = False,
        enricher_mode: str = "primary_with_fallback",
    ) -> Dict[str, Any]:
        """
        Builds/updates the persistent ChromaDB collection using `jina-embeddings-v3`.
        Reads deduplicated chassis reviews from `reviews_deduplicated_v6.json` (`clean_profile_lists` +
        verified `scraped_editorial` chunks) or auto-converts Format A / Format B1 inputs, and rebuilds `./chroma_reviews_db`.
        """
        if Path(reviews_json_path).exists():
            reviews_json_path, _, _ = self.ensure_deduplicated_reviews_file(
                reviews_path=reviews_json_path,
                catalog_path=catalog_json_path,
                auto_enrich=auto_enrich,
                force_reenrich=force_reenrich,
                enricher_mode=enricher_mode,
            )

        if recalibrate_first and Path(reviews_json_path).exists():
            data = self.recalibrate_catalog_and_reviews(
                reviews_json_path,
                catalog_json_path,
                auto_enrich=False,
            )
        else:
            with open(reviews_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        return self.vector_store.build(data, chroma_dir=chroma_dir, model_name=model_name)


_DEFAULT_SERVICE: Optional[ReviewsIngestionService] = None


def _get_default_service() -> ReviewsIngestionService:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = ReviewsIngestionService()
    return _DEFAULT_SERVICE


def ensure_deduplicated_reviews_file(
    reviews_path: str,
    catalog_path: str = "unified_catalog_topsis_ready_v6.json",
    auto_enrich: bool = True,
    force_reenrich: bool = False,
    enricher_mode: str = "primary_with_fallback",
) -> tuple[str, str, Optional[Dict[str, Any]]]:
    return _get_default_service().ensure_deduplicated_reviews_file(
        reviews_path=reviews_path,
        catalog_path=catalog_path,
        auto_enrich=auto_enrich,
        force_reenrich=force_reenrich,
        enricher_mode=enricher_mode,
    )


def recalibrate_catalog_and_reviews(
    reviews_path: str = "reviews_deduplicated_v6.json",
    catalog_path: str = "unified_catalog_topsis_ready_v6.json",
    auto_enrich: bool = True,
    force_reenrich: bool = False,
    enricher_mode: str = "primary_with_fallback",
) -> Dict[str, Any]:
    return _get_default_service().recalibrate_catalog_and_reviews(
        reviews_path=reviews_path,
        catalog_path=catalog_path,
        auto_enrich=auto_enrich,
        force_reenrich=force_reenrich,
        enricher_mode=enricher_mode,
    )


def build_chroma_reviews_db(
    reviews_json_path: str = "reviews_deduplicated_v6.json",
    catalog_json_path: str = "unified_catalog_topsis_ready_v6.json",
    chroma_dir: str = CHROMA_DEFAULT_DIR,
    model_name: str = MODEL_NAME,
    recalibrate_first: bool = True,
    auto_enrich: bool = True,
    force_reenrich: bool = False,
    enricher_mode: str = "primary_with_fallback",
) -> Dict[str, Any]:
    return _get_default_service().build_chroma_reviews_db(
        reviews_json_path=reviews_json_path,
        catalog_json_path=catalog_json_path,
        chroma_dir=chroma_dir,
        model_name=model_name,
        recalibrate_first=recalibrate_first,
        auto_enrich=auto_enrich,
        force_reenrich=force_reenrich,
        enricher_mode=enricher_mode,
    )
