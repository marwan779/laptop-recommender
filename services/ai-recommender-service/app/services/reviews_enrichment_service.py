"""Application service orchestrating review enrichment use-cases.

Pure chunking/scoring/recalibration live in `app.domain`; HTTP, model loading and
file persistence are injected through infrastructure adapters.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from app.domain.enrichment.chunking import (
    _format_catalog_specs_summary,
    compute_chassis_delta_hash,
    detect_reviews_format,
)
from app.domain.enrichment.models import (
    ASPECT_KEYS,
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_PRIMARY_MODEL,
    ENRICHER_SCHEMA_VERSION,
    _ASPECT_FALLBACK_AR,
    _ASPECT_FALLBACK_EN,
)
from app.domain.enrichment.scoring import (
    _build_llm_messages,
    _finalize_profile_with_recalibration,
    build_unreviewed_profile,
    is_valid_nlp_profile,
    validate_enriched_profile,
)
from app.infrastructure.delta_cache_repository import (
    JsonCatalogSpecsProvider,
    JsonDeltaCacheRepository,
    _save_json_atomic,
)
from app.infrastructure.jina_embedder import JinaPassageScorer
from app.infrastructure.protocols import (
    ICatalogSpecsProvider,
    IDeltaCacheRepository,
    ILLMClient,
)
from app.infrastructure.sovereigneg_client import SovereignEGClient, load_enricher_env

LLMCaller = Callable[..., Tuple[Optional[Dict[str, Any]], Dict[str, Any]]]


class ReviewsEnrichmentService:
    """Dependency-injected orchestrator for the raw -> enriched review pipeline."""

    def __init__(
        self,
        scorer: Optional[JinaPassageScorer] = None,
        llm_client: Optional[ILLMClient] = None,
        delta_cache_repository: Optional[IDeltaCacheRepository] = None,
        catalog_provider: Optional[ICatalogSpecsProvider] = None,
    ) -> None:
        self.scorer = scorer or JinaPassageScorer()
        self.llm_client = llm_client or SovereignEGClient()
        self.delta_cache_repository = delta_cache_repository or JsonDeltaCacheRepository()
        self.catalog_provider = catalog_provider or JsonCatalogSpecsProvider()

    @staticmethod
    def _has_real_evidence(evidence_pack: Dict[str, Any]) -> bool:
        return bool(evidence_pack.get("snippets")) or int(evidence_pack.get("doc_count") or 0) > 0

    @staticmethod
    def _skipped_no_evidence_result(start_ts: float) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return build_unreviewed_profile(), {
            "model_used": None,
            "path_taken": "skipped_no_evidence",
            "fallback_triggered": False,
            "raw_aspect_scores": {k: 75.0 for k in ASPECT_KEYS},
            "latency_sec": round(time.perf_counter() - start_ts, 4),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_egp": 0.0,
            "valid": False,
            "validation_errors": ["no_scraped_evidence"],
        }

    # ------------------------------------------------------------------
    # Mode A: Zero-LLM grounded enrichment (offline fallback)
    # ------------------------------------------------------------------
    def enrich_chassis_zero_llm(
        self,
        item: Dict[str, Any],
        cat_map: Optional[Dict[str, Any]] = None,
        evidence_pack: Optional[Dict[str, Any]] = None,
        preserve_existing_bullets: bool = False,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Build a complete `nlp_review_profile` using only local Jina-v3 anchor scores,
        extracted hardware evidence snippets, and verified catalog specifications.
        Returns `(nlp_review_profile, telemetry)`.
        """
        t0 = time.perf_counter()
        if evidence_pack is None:
            evidence_pack = self.scorer.extract_hardware_sentences_jina(item, cat_map=cat_map)

        if not self._has_real_evidence(evidence_pack):
            return self._skipped_no_evidence_result(t0)

        specs = evidence_pack.get("specs_summary") or _format_catalog_specs_summary(item, cat_map)
        snippets = evidence_pack.get("snippets") or []
        base_aspects = dict(evidence_pack.get("jina_aspect_scores_raw") or {})

        pros_en: List[str] = []
        pros_ar: List[str] = []
        cons_en: List[str] = []
        cons_ar: List[str] = []

        ranked_high = sorted(ASPECT_KEYS, key=lambda k: base_aspects.get(k, 72.0), reverse=True)
        ranked_low = sorted(ASPECT_KEYS, key=lambda k: base_aspects.get(k, 72.0))

        # Build aspect-grounded pros & cons from top Jina-selected snippets, avoiding repeated Arabic templates
        pro_snips = [s for s in snippets if s.get("polarity") == "pro"]
        con_snips = [s for s in snippets if s.get("polarity") == "con"]
        used_pro_aspects: set[str] = set()
        used_con_aspects: set[str] = set()

        for snip in pro_snips[:3]:
            asp = snip.get("aspect", "build_and_hinges_score")
            txt = snip["text"].strip()
            pros_en.append(f"[{snip['source']}] {txt}")
            ar_asp = asp if asp not in used_pro_aspects else next((a for a in ranked_high if a not in used_pro_aspects), asp)
            used_pro_aspects.add(ar_asp)
            pros_ar.append(f"{_ASPECT_FALLBACK_AR[ar_asp][0]} — بناءً على مراجعة ({snip['source']})")

        for snip in con_snips[:3]:
            asp = snip.get("aspect", "thermals_score")
            txt = snip["text"].strip()
            cons_en.append(f"[{snip['source']}] {txt}")
            ar_asp = asp if asp not in used_con_aspects else next((a for a in ranked_low if a not in used_con_aspects), asp)
            used_con_aspects.add(ar_asp)
            cons_ar.append(f"{_ASPECT_FALLBACK_AR[ar_asp][1]} — ملاحظة من ({snip['source']})")

        # Backfill from verified catalog hardware specs so every list always has 2..4 rich bullets
        cpu = specs.get("cpu") or "modern multi-core processor"
        gpu = specs.get("gpu") or "integrated/discrete graphics"
        srgb = specs.get("display_srgb_pct")
        whr = specs.get("battery_whr")
        panel = specs.get("display_panel") or "IPS"

        if len(pros_en) < 2:
            spec_pro_en = f"Equipped with {cpu} and {gpu} tailored for dependable {specs.get('category') or 'everyday'} workloads."
            spec_pro_ar = f"يقدم أداءً قوياً ومستقراً بفضل معالج {cpu} وكارت {gpu} مع شاشة {panel} مناسبة للاستخدام اليومي."
            pros_en.append(spec_pro_en)
            pros_ar.append(spec_pro_ar)
            for asp in ranked_high:
                if len(pros_en) >= 3:
                    break
                if asp in used_pro_aspects:
                    continue
                used_pro_aspects.add(asp)
                pros_en.append(_ASPECT_FALLBACK_EN[asp][0])
                pros_ar.append(_ASPECT_FALLBACK_AR[asp][0])

        if len(cons_en) < 2:
            if srgb and float(srgb) < 85:
                cons_en.append(f"Display color gamut (~{srgb}% sRGB) is limited for color-critical creative work.")
                cons_ar.append(f"تغطية ألوان الشاشة محدودة نسبياً ({srgb}% sRGB) ولا تناسب أعمال التصميم الدقيقة.")
            if whr and float(whr) <= 58 and "gaming" in str(specs.get("category") or "").lower():
                cons_en.append(f"Compact {whr}Wh battery delivers shorter unplugged runtime under heavy workloads.")
                cons_ar.append(f"البطارية بسعة {whr}Wh تمنح ساعات تشغيل محدودة خارج الشاحن تحت الاستخدام القوي.")
            for asp in ranked_low:
                if len(cons_en) >= 2:
                    break
                if asp in used_con_aspects:
                    continue
                used_con_aspects.add(asp)
                cons_en.append(_ASPECT_FALLBACK_EN[asp][1])
                cons_ar.append(_ASPECT_FALLBACK_AR[asp][1])

        pros_en = pros_en[:4]
        pros_ar = pros_ar[:4]
        cons_en = cons_en[:4]
        cons_ar = cons_ar[:4]

        evidence_count = max(1, len(snippets) + int(evidence_pack.get("doc_count") or 0))
        prof = _finalize_profile_with_recalibration(
            item=item,
            base_aspects=base_aspects,
            pros_en=pros_en,
            pros_ar=pros_ar,
            cons_en=cons_en,
            cons_ar=cons_ar,
            evidence_count=evidence_count,
            cat_map=cat_map,
            preserve_existing_bullets=preserve_existing_bullets,
        )
        elapsed = round(time.perf_counter() - t0, 4)
        telemetry = {
            "model_used": "zero_llm",
            "path_taken": "zero_llm",
            "fallback_triggered": False,
            "raw_aspect_scores": {k: round(float(base_aspects.get(k, 72.0)), 1) for k in ASPECT_KEYS},
            "latency_sec": elapsed,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_egp": 0.0,
            "valid": True,
            "validation_errors": [],
        }
        return prof, telemetry

    # ------------------------------------------------------------------
    # Mode B: LLM primary -> fallback -> zero_llm chain
    # ------------------------------------------------------------------
    def enrich_chassis_with_fallback(
        self,
        item: Dict[str, Any],
        cat_map: Optional[Dict[str, Any]] = None,
        evidence_pack: Optional[Dict[str, Any]] = None,
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        mode: str = "primary_with_fallback",
        preserve_existing_bullets: bool = False,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        llm_caller: Optional[LLMCaller] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Enrich one chassis using:
          - mode='zero_llm': local Jina-v3 anchor scoring only.
          - mode='single_model': call `primary_model` only (still falls back to `zero_llm` if fail).
          - mode='primary_with_fallback': call `primary_model` -> if schema/Arabic check fails,
            retry on `fallback_model` -> if still invalid/offline, fall back to `zero_llm`.
        """
        if evidence_pack is None:
            evidence_pack = self.scorer.extract_hardware_sentences_jina(item, cat_map=cat_map)

        if not self._has_real_evidence(evidence_pack):
            return self._skipped_no_evidence_result(time.perf_counter())

        if mode == "zero_llm":
            return self.enrich_chassis_zero_llm(
                item=item,
                cat_map=cat_map,
                evidence_pack=evidence_pack,
                preserve_existing_bullets=preserve_existing_bullets,
            )

        load_enricher_env()
        p_model = (primary_model or os.getenv("ENRICHER_PRIMARY_MODEL") or DEFAULT_PRIMARY_MODEL).strip()
        f_model = (fallback_model or os.getenv("ENRICHER_FALLBACK_MODEL") or DEFAULT_FALLBACK_MODEL).strip()
        caller = llm_caller or self.llm_client
        messages = _build_llm_messages(item, evidence_pack)

        models_to_try = [p_model]
        if mode == "primary_with_fallback" and f_model and f_model != p_model:
            models_to_try.append(f_model)

        total_latency = 0.0
        total_ptok = 0
        total_ctok = 0
        total_rtok = 0
        total_cost = 0.0
        attempts: List[Dict[str, Any]] = []

        for idx, model_name in enumerate(models_to_try):
            parsed, tel = caller(model_name, messages, base_url=base_url, api_key=api_key)
            total_latency += float(tel.get("latency_sec") or 0.0)
            total_ptok += int(tel.get("prompt_tokens") or 0)
            total_ctok += int(tel.get("completion_tokens") or 0)
            total_rtok += int(tel.get("reasoning_tokens") or 0)
            total_cost += float(tel.get("estimated_cost_egp") or 0.0)

            if parsed is not None:
                ok, errs = validate_enriched_profile(parsed)
            else:
                ok, errs = False, [str(tel.get("error") or "LLM call failed")]

            attempts.append({"model": model_name, "valid": ok, "errors": errs, "telemetry": tel})
            if ok and parsed is not None:
                raw_aspects = {k: float(parsed["aspect_scores"][k]) for k in ASPECT_KEYS}
                pros_en = [str(s).strip() for s in parsed["pros_en"] if str(s).strip()][:6]
                pros_ar = [str(s).strip() for s in parsed["pros_ar"] if str(s).strip()][:6]
                cons_en = [str(s).strip() for s in parsed["cons_en"] if str(s).strip()][:6]
                cons_ar = [str(s).strip() for s in parsed["cons_ar"] if str(s).strip()][:6]

                evidence_count = max(
                    1,
                    len(evidence_pack.get("snippets") or []) + int(evidence_pack.get("doc_count") or 0),
                )
                prof = _finalize_profile_with_recalibration(
                    item=item,
                    base_aspects=raw_aspects,
                    pros_en=pros_en,
                    pros_ar=pros_ar,
                    cons_en=cons_en,
                    cons_ar=cons_ar,
                    evidence_count=evidence_count,
                    cat_map=cat_map,
                    preserve_existing_bullets=preserve_existing_bullets,
                )
                return prof, {
                    "model_used": model_name,
                    "path_taken": "primary" if idx == 0 else "fallback",
                    "fallback_triggered": idx > 0,
                    "raw_aspect_scores": {k: round(raw_aspects[k], 1) for k in ASPECT_KEYS},
                    "latency_sec": round(total_latency, 4),
                    "prompt_tokens": total_ptok,
                    "completion_tokens": total_ctok,
                    "reasoning_tokens": total_rtok,
                    "total_tokens": total_ptok + total_ctok,
                    "estimated_cost_egp": round(total_cost, 6),
                    "valid": True,
                    "validation_errors": [],
                    "attempts": attempts,
                }

        # Automatic offline zero_llm fallback if Primary & Fallback both failed
        prof, z_tel = self.enrich_chassis_zero_llm(
            item=item,
            cat_map=cat_map,
            evidence_pack=evidence_pack,
            preserve_existing_bullets=preserve_existing_bullets,
        )
        z_tel["path_taken"] = "zero_llm_fallback"
        z_tel["fallback_triggered"] = True
        z_tel["latency_sec"] = round(total_latency + float(z_tel["latency_sec"]), 4)
        z_tel["prompt_tokens"] = total_ptok
        z_tel["completion_tokens"] = total_ctok
        z_tel["reasoning_tokens"] = total_rtok
        z_tel["total_tokens"] = total_ptok + total_ctok
        z_tel["estimated_cost_egp"] = round(total_cost, 6)
        z_tel["attempts"] = attempts
        return prof, z_tel

    # ------------------------------------------------------------------
    # Dataset-wide batch enricher
    # ------------------------------------------------------------------
    def enrich_reviews_dataset(
        self,
        payload_or_path: Union[str, Path, Dict[str, Any]],
        catalog_path: str = "unified_catalog_topsis_ready_v6.json",
        delta_cache_path: Optional[str] = "enricher_delta_cache.json",
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        mode: str = "primary_with_fallback",
        force: bool = False,
        only_missing_or_delta: bool = True,
        max_workers: int = 8,
        preserve_existing_bullets: bool = False,
        output_path: Optional[str] = None,
        llm_caller: Optional[LLMCaller] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Enrich all new or changed chassis in a Format A / partial Format B1 dataset into
        complete Enriched Format B1, updating `delta_cache_path` and optionally saving to `output_path`.

        - Runs local `Jina-v3` evidence extraction sequentially on delta misses (PyTorch-safe).
        - Executes remote SovereignEG LLM calls concurrently via `ThreadPoolExecutor(max_workers=max_workers)`.
        """
        if isinstance(payload_or_path, dict):
            data = json.loads(json.dumps(payload_or_path))
        else:
            with open(payload_or_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        fmt = detect_reviews_format(data)
        if fmt == "format_b2_deduplicated":
            return data, {
                "detected_format": fmt,
                "total_chassis": len(data.get("chassis_reviews", [])),
                "enriched_count": 0,
                "cache_hits": len(data.get("chassis_reviews", [])),
                "note": "Already deduplicated Format B2; no raw enrichment needed.",
            }

        cat_map: Optional[Dict[str, Any]] = None
        if catalog_path and Path(catalog_path).exists():
            cat_map = self.catalog_provider.load_map(catalog_path)

        load_enricher_env()
        eff_primary = (primary_model or os.getenv("ENRICHER_PRIMARY_MODEL") or DEFAULT_PRIMARY_MODEL).strip()

        delta_cache = self.delta_cache_repository.load(delta_cache_path)
        entries = delta_cache.setdefault("entries", {})

        laptops: List[Dict[str, Any]] = data.get("laptops", [])
        work_queue: List[Tuple[int, str, Dict[str, Any]]] = []
        cache_hits = 0

        for idx, item in enumerate(laptops):
            if not isinstance(item, dict):
                continue
            ckey = str(item.get("chassis_key") or f"chassis_{idx}")
            dhash = compute_chassis_delta_hash(item, cat_map=cat_map)
            has_valid_prof = is_valid_nlp_profile(item.get("nlp_review_profile"))
            cached = entries.get(ckey) or {}
            cached_model = str(cached.get("model_used") or "")
            model_match = True
            if mode != "zero_llm" and cached_model and cached_model != "curated_preserved":
                model_match = (cached_model == eff_primary)
            cache_match = (
                not force
                and only_missing_or_delta
                and has_valid_prof
                and cached.get("delta_hash") == dhash
                and model_match
            )
            if cache_match:
                cache_hits += 1
                continue
            work_queue.append((idx, dhash, item))

        # Stage 1: Batched length-sorted Jina-v3 sentence filtering & anchor scoring for delta misses
        evidence_packs: Dict[int, Dict[str, Any]] = {}
        if work_queue:
            batch_packs = self.scorer.extract_hardware_sentences_jina_batch(
                [item for _, _, item in work_queue],
                cat_map=cat_map,
            )
            for (idx, _, _), pack in zip(work_queue, batch_packs):
                evidence_packs[idx] = pack

        # Stage 2: Concurrent SovereignEG Primary -> Fallback (or sequential zero_llm)
        path_counts: Dict[str, int] = {
            "primary": 0,
            "fallback": 0,
            "zero_llm": 0,
            "zero_llm_fallback": 0,
        }
        total_cost_egp = 0.0
        total_prompt_tokens = 0
        total_completion_tokens = 0

        def _process_one(job: Tuple[int, str, Dict[str, Any]]) -> Tuple[int, str, Dict[str, Any], Dict[str, Any]]:
            j_idx, j_hash, j_item = job
            prof, tel = self.enrich_chassis_with_fallback(
                item=j_item,
                cat_map=cat_map,
                evidence_pack=evidence_packs[j_idx],
                primary_model=primary_model,
                fallback_model=fallback_model,
                mode=mode,
                preserve_existing_bullets=preserve_existing_bullets,
                llm_caller=llm_caller,
            )
            return j_idx, j_hash, prof, tel

        def _record_result(j_idx: int, j_hash: str, prof: Dict[str, Any], tel: Dict[str, Any]) -> None:
            nonlocal total_cost_egp, total_prompt_tokens, total_completion_tokens
            laptops[j_idx]["nlp_review_profile"] = prof
            ckey = str(laptops[j_idx].get("chassis_key") or f"chassis_{j_idx}")
            ptaken = str(tel.get("path_taken") or "zero_llm")
            path_counts[ptaken] = path_counts.get(ptaken, 0) + 1
            total_cost_egp += float(tel.get("estimated_cost_egp") or 0.0)
            total_prompt_tokens += int(tel.get("prompt_tokens") or 0)
            total_completion_tokens += int(tel.get("completion_tokens") or 0)
            if ptaken != "skipped_no_evidence" and (mode == "zero_llm" or ptaken in ("primary", "fallback")):
                entries[ckey] = {
                    "delta_hash": j_hash,
                    "model_used": tel.get("model_used"),
                    "path_taken": ptaken,
                    "evidence_count": prof.get("evidence_count"),
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }

        completed_count = 0
        if mode == "zero_llm" or len(work_queue) <= 1:
            for job in work_queue:
                j_idx, j_hash, prof, tel = _process_one(job)
                _record_result(j_idx, j_hash, prof, tel)
                completed_count += 1
        else:
            workers = max(1, min(int(max_workers), len(work_queue)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = [pool.submit(_process_one, job) for job in work_queue]
                for fut in as_completed(futs):
                    j_idx, j_hash, prof, tel = fut.result()
                    _record_result(j_idx, j_hash, prof, tel)
                    completed_count += 1
                    if completed_count % 25 == 0 or completed_count == len(work_queue):
                        print(
                            f"  [Enricher Stage 2] {completed_count}/{len(work_queue)} completed "
                            f"(primary={path_counts['primary']}, fallback={path_counts['fallback']}, "
                            f"zero_llm={path_counts['zero_llm_fallback']}, cost={total_cost_egp:.4f} EGP)"
                        )
                        if delta_cache_path:
                            delta_cache["schema_version"] = ENRICHER_SCHEMA_VERSION
                            self.delta_cache_repository.save(delta_cache_path, delta_cache)
                        if output_path:
                            _save_json_atomic(output_path, data)

        if isinstance(data.get("batch_metadata"), dict):
            data["batch_metadata"]["last_enrichment_mode"] = mode
            data["batch_metadata"]["total_chassis"] = len(laptops)

        if delta_cache_path and completed_count:
            delta_cache["schema_version"] = ENRICHER_SCHEMA_VERSION
            self.delta_cache_repository.save(delta_cache_path, delta_cache)

        if output_path:
            _save_json_atomic(output_path, data)

        summary = {
            "detected_format": fmt,
            "total_chassis": len(laptops),
            "cache_hits": cache_hits,
            "enriched_count": completed_count,
            "enriched_via_primary": path_counts.get("primary", 0),
            "enriched_via_fallback": path_counts.get("fallback", 0),
            "enriched_via_zero_llm": path_counts.get("zero_llm", 0) + path_counts.get("zero_llm_fallback", 0),
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "estimated_cost_egp": round(total_cost_egp, 6),
        }
        return data, summary


# ---------------------------------------------------------------------------
# Module-level compatibility wrappers (preserve historic public signatures)
# ---------------------------------------------------------------------------

_DEFAULT_SERVICE: Optional[ReviewsEnrichmentService] = None


def _get_default_service() -> ReviewsEnrichmentService:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = ReviewsEnrichmentService()
    return _DEFAULT_SERVICE


def enrich_chassis_zero_llm(
    item: Dict[str, Any],
    cat_map: Optional[Dict[str, Any]] = None,
    evidence_pack: Optional[Dict[str, Any]] = None,
    preserve_existing_bullets: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return _get_default_service().enrich_chassis_zero_llm(
        item=item,
        cat_map=cat_map,
        evidence_pack=evidence_pack,
        preserve_existing_bullets=preserve_existing_bullets,
    )


def enrich_chassis_with_fallback(
    item: Dict[str, Any],
    cat_map: Optional[Dict[str, Any]] = None,
    evidence_pack: Optional[Dict[str, Any]] = None,
    primary_model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    mode: str = "primary_with_fallback",
    preserve_existing_bullets: bool = False,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    llm_caller: Optional[LLMCaller] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return _get_default_service().enrich_chassis_with_fallback(
        item=item,
        cat_map=cat_map,
        evidence_pack=evidence_pack,
        primary_model=primary_model,
        fallback_model=fallback_model,
        mode=mode,
        preserve_existing_bullets=preserve_existing_bullets,
        base_url=base_url,
        api_key=api_key,
        llm_caller=llm_caller,
    )


def enrich_reviews_dataset(
    payload_or_path: Union[str, Path, Dict[str, Any]],
    catalog_path: str = "unified_catalog_topsis_ready_v6.json",
    delta_cache_path: Optional[str] = "enricher_delta_cache.json",
    primary_model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    mode: str = "primary_with_fallback",
    force: bool = False,
    only_missing_or_delta: bool = True,
    max_workers: int = 8,
    preserve_existing_bullets: bool = False,
    output_path: Optional[str] = None,
    llm_caller: Optional[LLMCaller] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return _get_default_service().enrich_reviews_dataset(
        payload_or_path=payload_or_path,
        catalog_path=catalog_path,
        delta_cache_path=delta_cache_path,
        primary_model=primary_model,
        fallback_model=fallback_model,
        mode=mode,
        force=force,
        only_missing_or_delta=only_missing_or_delta,
        max_workers=max_workers,
        preserve_existing_bullets=preserve_existing_bullets,
        output_path=output_path,
        llm_caller=llm_caller,
    )


if __name__ == "__main__":
    import argparse
    from app.domain.enrichment.models import DEFAULT_DELTA_CACHE_PATH
    from app.infrastructure.sovereigneg_client import load_enricher_env

    load_enricher_env()

    parser = argparse.ArgumentParser(description="Enrich Format A raw chassis reviews into Format B1.")
    parser.add_argument("--input", default="cleaned_and_enriched_chassis_reviews_v6.json")
    parser.add_argument("--output", default="cleaned_and_enriched_chassis_reviews_v6.json")
    parser.add_argument("--catalog", default="unified_catalog_topsis_ready_v6.json")
    parser.add_argument("--cache", default=DEFAULT_DELTA_CACHE_PATH)
    parser.add_argument(
        "--mode",
        default="primary_with_fallback",
        choices=["primary_with_fallback", "single_model", "zero_llm"],
    )
    parser.add_argument("--primary-model", default=None)
    parser.add_argument("--fallback-model", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    cli_args = parser.parse_args()

    _, summary = enrich_reviews_dataset(
        payload_or_path=cli_args.input,
        catalog_path=cli_args.catalog,
        delta_cache_path=cli_args.cache,
        primary_model=cli_args.primary_model,
        fallback_model=cli_args.fallback_model,
        mode=cli_args.mode,
        force=cli_args.force,
        max_workers=cli_args.workers,
        output_path=cli_args.output,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
