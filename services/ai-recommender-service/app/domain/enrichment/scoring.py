"""Pure review-scoring, prompt-building, validation and synthesis domain logic.

Only stdlib + numpy array math is used here.  Model loading, HTTP calls and file
persistence live in the infrastructure layer.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.domain.enrichment.models import (
    _ARABIC_CHAR_RE,
    _ASPECT_FALLBACK_AR,
    _ASPECT_FALLBACK_EN,
    _ASPECT_KEYWORDS,
    _CODE_BLOCK_RE,
    _DETAILS_BLOCK_RE,
    _HTML_TAG_RE,
    _THINK_TAG_RE,
    _URL_RE,
    ASPECT_KEYS,
    SOVEREIGNEG_PRICING_EGP_PER_1M,
)


# ---------------------------------------------------------------------------
# Format Detection & Profile Schema Validation
# ---------------------------------------------------------------------------

def is_valid_nlp_profile(prof: Any) -> bool:
    """Quick structural check for an existing Format B1 `nlp_review_profile`."""
    ok, _ = validate_enriched_profile(prof)
    return ok


def validate_enriched_profile(prof: Any) -> Tuple[bool, List[str]]:
    """
    Validate an enriched profile (either raw LLM output or complete `nlp_review_profile`).

    Checks:
    - All 5 aspect_scores exist, are finite numbers, and lie strictly in [35.0, 98.0].
    - `pros_en`, `pros_ar`, `cons_en`, `cons_ar` each contain 2 to 6 non-empty strings.
    - Every string in `pros_ar` and `cons_ar` contains >= 10 Arabic characters (`\u0600-\u06FF`).
    """
    errors: List[str] = []
    if not isinstance(prof, dict):
        return False, ["profile is not a JSON object"]

    aspects = prof.get("aspect_scores")
    if not isinstance(aspects, dict):
        errors.append("missing or invalid aspect_scores object")
    else:
        for k in ASPECT_KEYS:
            val = aspects.get(k)
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                errors.append(f"aspect_scores.{k} is not numeric")
                continue
            fval = float(val)
            if not math.isfinite(fval) or fval < 35.0 or fval > 98.0:
                errors.append(f"aspect_scores.{k}={fval} out of range [35.0, 98.0]")

    for list_key in ("pros_en", "pros_ar", "cons_en", "cons_ar"):
        items = prof.get(list_key)
        if not isinstance(items, list):
            errors.append(f"{list_key} is not a list")
            continue
        cleaned = [str(x).strip() for x in items if isinstance(x, str) and str(x).strip()]
        if not (2 <= len(cleaned) <= 6):
            errors.append(f"{list_key} has {len(cleaned)} items (expected 2..6)")
            continue
        for idx, s in enumerate(cleaned):
            if len(s) < 10:
                errors.append(f"{list_key}[{idx}] too short ({len(s)} chars)")
            if list_key.endswith("_ar"):
                ar_count = len(_ARABIC_CHAR_RE.findall(s))
                if ar_count < 10:
                    errors.append(
                        f"{list_key}[{idx}] has only {ar_count} Arabic chars (min 10)"
                    )

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Pure Jina anchor scoring (no model loading)
# ---------------------------------------------------------------------------

def _compute_zero_llm_aspect_scores(
    selected_rows: List[Dict[str, Any]],
    doc_count: int,
    specs: Dict[str, Any],
) -> Dict[str, float]:
    """Compute bounded [35.0, 98.0] raw baseline aspect scores using Jina anchor differentials + keyword signals."""
    cat = str(specs.get("category") or "").lower()
    is_gaming = "gaming" in cat or bool(re.search(r"rtx\s*[345]0\d\d|gtx|radeon rx", str(specs.get("gpu") or "").lower()))
    whr = float(specs.get("battery_whr") or (70.0 if is_gaming else 56.0))
    is_metal = bool(specs.get("verified_metal_chassis")) or "alum" in str(specs.get("chassis_material") or "").lower()

    # Prior baseline by category & verified hardware properties
    priors: Dict[str, float] = {
        "thermals_score": 73.0 if is_gaming else 76.0,
        "acoustics_score": 66.0 if is_gaming else 76.0,
        "build_and_hinges_score": 82.0 if is_metal else 73.0,
        "keyboard_and_trackpad_score": 76.0 if is_metal else 74.0,
        "real_battery_and_reliability_score": (
            77.0 if (not is_gaming and whr >= 65.0) else (62.0 if (is_gaming and whr <= 58.0) else 70.0)
        ),
    }

    scores: Dict[str, float] = {}
    for idx, k in enumerate(ASPECT_KEYS):
        base = priors[k]
        if not selected_rows:
            scores[k] = round(max(35.0, min(98.0, base)), 1)
            continue

        pro_vals = [float(r["pro_sims"][idx]) for r in selected_rows]
        con_vals = [float(r["con_sims"][idx]) for r in selected_rows]
        top_pro = sorted(pro_vals, reverse=True)[:5]
        top_con = sorted(con_vals, reverse=True)[:5]
        sem_diff = float(np.mean(top_pro)) - float(np.mean(top_con))

        kw_pro = sum(
            1
            for r in selected_rows
            if any(tok in r["text"].lower() for tok in _ASPECT_KEYWORDS[k]["pro"])
        )
        kw_con = sum(
            1
            for r in selected_rows
            if any(tok in r["text"].lower() for tok in _ASPECT_KEYWORDS[k]["con"])
        )

        # Combine semantic pro-vs-con margin and explicit keyword sentiment
        evidence_scale = min(1.0, max(0.35, len(selected_rows) / 14.0))
        delta = (sem_diff * 155.0 + (kw_pro - kw_con) * 3.2) * evidence_scale
        # Keep mild damping so gaming/budget laptops reflect acoustics/battery realities
        val = max(35.0, min(95.0, base + delta))
        scores[k] = round(val, 1)

    return scores


def _score_snippets_from_vectors(
    chassis_key: str,
    unique_cands: List[Dict[str, Any]],
    doc_count: int,
    specs_summary: Dict[str, Any],
    vecs: np.ndarray,
    anchors: Dict[str, Any],
    max_snippets: int = 20,
    dedup_cosine: float = 0.88,
) -> Dict[str, Any]:
    """Pure 10-anchor cosine scoring, noise rejection, and cosine dedup for one chassis."""
    if not unique_cands or len(vecs) == 0:
        return {
            "chassis_key": chassis_key,
            "doc_count": doc_count,
            "candidate_count": 0,
            "snippets": [],
            "jina_aspect_pro_mean": {k: 0.0 for k in ASPECT_KEYS},
            "jina_aspect_con_mean": {k: 0.0 for k in ASPECT_KEYS},
            "jina_aspect_scores_raw": _compute_zero_llm_aspect_scores([], doc_count=doc_count, specs=specs_summary),
            "specs_summary": specs_summary,
        }

    pro_sims = vecs @ anchors["pro"].T  # (N, 5)
    con_sims = vecs @ anchors["con"].T  # (N, 5)
    noise_sims = vecs @ anchors["noise"]  # (N,)

    all_sims = np.concatenate([pro_sims, con_sims], axis=1)  # (N, 10)
    max_hw_sim = all_sims.max(axis=1)
    best_idx = all_sims.argmax(axis=1)

    scored_rows: List[Dict[str, Any]] = []
    for i, cand in enumerate(unique_cands):
        hw_score = float(max_hw_sim[i])
        n_score = float(noise_sims[i])
        if n_score > hw_score + 0.03 and hw_score < 0.36:
            continue
        aspect_idx = int(best_idx[i]) % 5
        polarity = "pro" if int(best_idx[i]) < 5 else "con"
        relevance = (hw_score - 0.35 * max(0.0, n_score - 0.25)) * float(cand["source_weight"])
        scored_rows.append(
            {
                "idx": i,
                "text": cand["text"],
                "source": cand["source"],
                "aspect": ASPECT_KEYS[aspect_idx],
                "polarity": polarity,
                "hw_sim": round(hw_score, 4),
                "noise_sim": round(n_score, 4),
                "relevance": round(relevance, 4),
                "pro_sims": pro_sims[i],
                "con_sims": con_sims[i],
                "vec": vecs[i],
            }
        )

    scored_rows.sort(key=lambda r: r["relevance"], reverse=True)
    selected: List[Dict[str, Any]] = []
    selected_vecs: List[np.ndarray] = []

    def _is_dup(vec: np.ndarray) -> bool:
        if not selected_vecs:
            return False
        mat = np.stack(selected_vecs)
        return float((mat @ vec).max()) > dedup_cosine

    aspect_counts = {k: 0 for k in ASPECT_KEYS}
    for asp in ASPECT_KEYS:
        for row in scored_rows:
            if len(selected) >= max_snippets:
                break
            if row["aspect"] == asp and aspect_counts[asp] < 2 and not _is_dup(row["vec"]):
                selected.append(row)
                selected_vecs.append(row["vec"])
                aspect_counts[asp] += 1
                row["_picked"] = True

    for row in scored_rows:
        if len(selected) >= max_snippets:
            break
        if row.get("_picked"):
            continue
        if not _is_dup(row["vec"]):
            selected.append(row)
            selected_vecs.append(row["vec"])
            row["_picked"] = True

    pro_means = {
        k: round(float(np.mean([r["pro_sims"][idx] for r in selected])), 4) if selected else 0.0
        for idx, k in enumerate(ASPECT_KEYS)
    }
    con_means = {
        k: round(float(np.mean([r["con_sims"][idx] for r in selected])), 4) if selected else 0.0
        for idx, k in enumerate(ASPECT_KEYS)
    }

    raw_scores = _compute_zero_llm_aspect_scores(selected, doc_count=doc_count, specs=specs_summary)
    clean_snippets = [
        {
            "text": r["text"],
            "source": r["source"],
            "aspect": r["aspect"],
            "polarity": r["polarity"],
            "relevance": r["relevance"],
        }
        for r in selected
    ]

    return {
        "chassis_key": chassis_key,
        "doc_count": doc_count,
        "candidate_count": len(unique_cands),
        "snippets": clean_snippets,
        "jina_aspect_pro_mean": pro_means,
        "jina_aspect_con_mean": con_means,
        "jina_aspect_scores_raw": raw_scores,
        "specs_summary": specs_summary,
    }


# ---------------------------------------------------------------------------
# LLM prompt building & response parsing
# ---------------------------------------------------------------------------

def _build_llm_messages(item: Dict[str, Any], evidence_pack: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build concise, hardware-grounded bilingual prompt from Jina-filtered snippets + specs."""
    specs = evidence_pack.get("specs_summary") or {}
    snippets = evidence_pack.get("snippets") or []
    jina_scores = evidence_pack.get("jina_aspect_scores_raw") or {}
    model_name = specs.get("laptop_model") or item.get("chassis_key") or "Laptop"

    snippets_lines = "\n".join(
        f"- [{s['source']} | {s['aspect']} | {s['polarity']}] {s['text']}"
        for s in snippets[:20]
    )
    if not snippets_lines:
        snippets_lines = "- No full-length user or YouTube transcript snippets scraped; rely strictly on verified catalog hardware specs below and state evidence limits honestly."

    system_msg = (
        "You are an expert laptop hardware engineer & Egyptian tech reviewer. "
        "Synthesize an accurate JSON review profile grounded strictly in the verified hardware specs and extracted review snippets. "
        "CRITICAL RULES:\n"
        "1. Output ONLY a single valid JSON object matching this schema:\n"
        "   - aspect_scores: {thermals_score, acoustics_score, build_and_hinges_score, keyboard_and_trackpad_score, real_battery_and_reliability_score} — each a number strictly between 35.0 and 98.0.\n"
        "   - pros_en: 3 to 5 concise, specific hardware strengths in English (mention thermals/cooling, display panel/Hz/nits/color, chassis/hinges, battery, and M.2/DDR5 upgradeability where supported).\n"
        "   - pros_ar: 3 to 5 matching strengths in clear technical/Egyptian-friendly Arabic (every item >= 15 Arabic characters; keep GPU/CPU/Hz/Wh/M.2/DDR5 specs in English).\n"
        "   - cons_en: 3 to 5 honest hardware weaknesses or trade-offs in English (mention loud fan noise, plastic flex/hinge wobble, dim 45% NTSC screen, battery drain, soldered non-upgradeable RAM, or GPU TGP/power limits where supported).\n"
        "   - cons_ar: 3 to 5 matching weaknesses/trade-offs in clear Arabic (every item >= 15 Arabic characters).\n"
        "2. Differentiate scores sharply using evidence (do NOT score everything 80-85): penalize loud Turbo fans (<65), thermal throttling (<65), plastic flex (<72), dim 45% NTSC displays or short battery (<62).\n"
        "3. Ignore any off-topic desktop GPU/motherboard or mismatched brand mentions."
    )

    user_msg = (
        f"Target Laptop: {specs.get('brand', '')} {model_name}\n"
        f"Chassis Key: {item.get('chassis_key', '')}\n"
        f"Verified Catalog Specs: {json.dumps(specs, ensure_ascii=False)}\n"
        f"Local Jina-v3 Anchor Baseline Scores (reference prior): {json.dumps(jina_scores)}\n\n"
        f"Top Jina-v3 Filtered Hardware Review Snippets ({len(snippets)} chunks across {evidence_pack.get('doc_count', 0)} docs):\n"
        f"{snippets_lines}"
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _extract_json_from_llm_content(raw_text: str) -> Any:
    """Strip reasoning tags and markdown code fences before parsing JSON."""
    if not raw_text:
        raise ValueError("Empty LLM response content")
    cleaned = _THINK_TAG_RE.sub("", raw_text).strip()
    if "```" in cleaned:
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if m:
            cleaned = m.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _estimate_egp_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Compute SovereignEG EGP cost from verified per-1M rates."""
    rates = SOVEREIGNEG_PRICING_EGP_PER_1M.get(model)
    if not rates:
        for k, v in SOVEREIGNEG_PRICING_EGP_PER_1M.items():
            if k in model.lower():
                rates = v
                break
    if not rates:
        return 0.0
    cost = (prompt_tokens / 1_000_000.0) * rates["input"] + (
        completion_tokens / 1_000_000.0
    ) * rates["output"]
    return round(cost, 6)


# ---------------------------------------------------------------------------
# Synthesized summary builders
# ---------------------------------------------------------------------------

def _build_synthesized_texts(
    model_label: str,
    specs: Dict[str, Any],
    base_aspects: Dict[str, float],
    pros_en: List[str],
    pros_ar: List[str],
    cons_en: List[str],
    cons_ar: List[str],
) -> Tuple[str, str]:
    """
    Build `synthesized_review_en` and `synthesized_review_ar` matching the exact B1 schema.
    Crucially embeds RAW `base_aspects` into `Aspect Ratings -> ...` so `chroma_reviews_engine`
    recalibration remains completely idempotent.
    """
    spec_bits = [b for b in [specs.get("cpu"), specs.get("gpu")] if b]
    spec_tag = f" ({', '.join(spec_bits)})" if spec_bits else ""
    ratings_str = (
        f"Thermals: {base_aspects['thermals_score']:.1f}/100, "
        f"Fan Noise/Acoustics: {base_aspects['acoustics_score']:.1f}/100, "
        f"Chassis Build & Hinges: {base_aspects['build_and_hinges_score']:.1f}/100, "
        f"Keyboard & Trackpad: {base_aspects['keyboard_and_trackpad_score']:.1f}/100, "
        f"Real Battery & Reliability: {base_aspects['real_battery_and_reliability_score']:.1f}/100"
    )
    en_text = (
        f"Technical Review Summary for {model_label}{spec_tag}: "
        f"Pros: {'; '.join(pros_en)}. "
        f"Cons & Trade-offs: {'; '.join(cons_en)}. "
        f"Aspect Ratings -> {ratings_str}."
    )
    ar_text = (
        f"ملخص المراجعة العملية وتجربة الاستخدام لجهاز {model_label}: "
        f"المميزات العملية: {' ؛ '.join(pros_ar)}. "
        f"العيوب والملاحظات: {' ؛ '.join(cons_ar)}."
    )
    return en_text, ar_text


def _finalize_profile_with_recalibration(
    item: Dict[str, Any],
    base_aspects: Dict[str, float],
    pros_en: List[str],
    pros_ar: List[str],
    cons_en: List[str],
    cons_ar: List[str],
    evidence_count: int,
    cat_map: Optional[Dict[str, Any]],
    preserve_existing_bullets: bool = False,
) -> Dict[str, Any]:
    """
    Finalize a Format B1 `nlp_review_profile` using `_recalibrate_item`
    while preserving raw baseline aspect scores in `synthesized_review_en`.
    """
    from app.domain.enrichment.chunking import _format_catalog_specs_summary
    from app.domain.reviews.calibration import _recalibrate_item

    ident = item.get("identity") or {}
    cids = list(item.get("matched_canonical_ids") or [])
    primary_cid = item.get("primary_canonical_id") or (cids[0] if cids else None)
    specs = _format_catalog_specs_summary(item, cat_map)
    model_label = str(ident.get("laptop_model") or specs.get("laptop_model") or item.get("chassis_key") or "Laptop")

    # Optionally merge non-duplicate existing verified bullets when enriching incrementally
    if preserve_existing_bullets and isinstance(item.get("nlp_review_profile"), dict):
        old_prof = item["nlp_review_profile"]
        pros_en = _merge_unique_bullets(pros_en, old_prof.get("pros_en") or [], cap=5)
        pros_ar = _merge_unique_bullets(pros_ar, old_prof.get("pros_ar") or [], cap=5, arabic_only=True)
        cons_en = _merge_unique_bullets(cons_en, old_prof.get("cons_en") or [], cap=5)
        cons_ar = _merge_unique_bullets(cons_ar, old_prof.get("cons_ar") or [], cap=5, arabic_only=True)

    # Enforce strict [35.0, 98.0] bounds on raw baseline scores before physical recalibration
    clean_base = {
        k: round(max(35.0, min(98.0, float(base_aspects.get(k, 72.0)))), 1)
        for k in ASPECT_KEYS
    }

    if cat_map is not None:
        recal = _recalibrate_item(ident, cids, primary_cid, clean_base, cat_map)
        final_aspects = recal["aspect_scores"]
        final_score = recal["community_nlp_score"]
    else:
        final_aspects = dict(clean_base)
        final_score = round(sum(final_aspects.values()) / len(ASPECT_KEYS), 2)

    syn_en, syn_ar = _build_synthesized_texts(
        model_label=model_label,
        specs=specs,
        base_aspects=clean_base,
        pros_en=pros_en,
        pros_ar=pros_ar,
        cons_en=cons_en,
        cons_ar=cons_ar,
    )

    return {
        "community_nlp_score": float(final_score),
        "evidence_count": int(max(1, evidence_count)),
        "aspect_scores": final_aspects,
        "pros_en": pros_en,
        "pros_ar": pros_ar,
        "cons_en": cons_en,
        "cons_ar": cons_ar,
        "synthesized_review_en": syn_en,
        "synthesized_review_ar": syn_ar,
    }


def _merge_unique_bullets(
    primary: List[str],
    secondary: Sequence[str],
    cap: int = 5,
    arabic_only: bool = False,
) -> List[str]:
    """Append complementary bullets from `secondary` if not lexically/semantically redundant."""
    out = list(primary[:cap])
    if len(out) >= cap or not secondary:
        return out

    norm_seen = {re.sub(r"\W+", " ", s.lower()).strip() for s in out}
    for cand in secondary:
        if len(out) >= cap:
            break
        if not isinstance(cand, str):
            continue
        c = cand.strip()
        if len(c) < 12:
            continue
        if arabic_only and len(_ARABIC_CHAR_RE.findall(c)) < 10:
            continue
        cnorm = re.sub(r"\W+", " ", c.lower()).strip()
        if cnorm in norm_seen:
            continue
        # Light token Jaccard check to skip near-duplicates quickly
        ctoks = set(cnorm.split())
        if any(len(ctoks & set(ex.split())) / max(1, len(ctoks | set(ex.split()))) > 0.55 for ex in norm_seen):
            continue
        out.append(c)
        norm_seen.add(cnorm)
    return out
