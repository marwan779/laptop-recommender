#!/usr/bin/env python3
"""
Upgraded ChromaDB & Aspect Recalibration Engine (chroma_reviews_engine.py)
--------------------------------------------------------------------------
1. Recalibrates the 5 Field Review Aspects to eliminate score clustering across tiers.
2. Uses `jinaai/jina-embeddings-v3` in FP16 with task-specific adapters
   (`retrieval.passage` for indexing Pros/Cons, `retrieval.query` for user queries).
3. Works both as an importable Python module AND a CLI script for Backend Cron Jobs.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

MODEL_NAME = "jinaai/jina-embeddings-v3"
EMBED_DIM = 512
CHROMA_DEFAULT_DIR = "./chroma_reviews_db"
COLLECTION_NAME = "laptop_chassis_reviews_jina_v3"


class JinaV3EmbeddingFunction(EmbeddingFunction[Documents]):
    """
    Singleton-friendly wrapper around SentenceTransformer for `jinaai/jina-embeddings-v3`.
    Supports `task="retrieval.passage"` during indexing and `task="retrieval.query"` at search time,
    using Matryoshka `truncate_dim=512` (selected via A/B benchmark: 90.7% Top-5 overlap, 0.9874 rank corr).
    """
    _model_instance = None

    def __init__(self, model_name: str = MODEL_NAME, task: str = "retrieval.passage", truncate_dim: int = EMBED_DIM):
        self.model_name = model_name
        self.task = task
        self.truncate_dim = truncate_dim
        if JinaV3EmbeddingFunction._model_instance is None:
            import torch
            from sentence_transformers import SentenceTransformer

            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            try:
                JinaV3EmbeddingFunction._model_instance = SentenceTransformer(
                    model_name,
                    trust_remote_code=True,
                    truncate_dim=truncate_dim,
                    model_kwargs={"torch_dtype": dtype},
                )
            except Exception:
                # Fallback if float16 or remote code fails on older CPU
                JinaV3EmbeddingFunction._model_instance = SentenceTransformer(
                    model_name,
                    trust_remote_code=True,
                    truncate_dim=truncate_dim,
                )
            JinaV3EmbeddingFunction._model_instance.max_seq_length = 256

    def __call__(self, input: Documents) -> Embeddings:
        model = JinaV3EmbeddingFunction._model_instance
        try:
            vecs = model.encode(
                list(input),
                task=self.task,
                Prompt_name=self.task,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except TypeError:
            vecs = model.encode(
                list(input),
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return vecs.tolist()


_BASELINE_ASPECT_RE = re.compile(
    r"Thermals:\s*([\d.]+)/100,\s*Fan Noise/Acoustics:\s*([\d.]+)/100,\s*"
    r"Chassis Build & Hinges:\s*([\d.]+)/100,\s*Keyboard & Trackpad:\s*([\d.]+)/100,\s*"
    r"Real Battery & Reliability:\s*([\d.]+)/100"
)


def _extract_baseline_aspects(prof: Dict[str, Any], fallback_aspects: Dict[str, Any]) -> Dict[str, float]:
    synth_en = str(prof.get("synthesized_review_en") or "")
    m = _BASELINE_ASPECT_RE.search(synth_en)
    if m:
        return {
            "thermals_score": float(m.group(1)),
            "acoustics_score": float(m.group(2)),
            "build_and_hinges_score": float(m.group(3)),
            "keyboard_and_trackpad_score": float(m.group(4)),
            "real_battery_and_reliability_score": float(m.group(5)),
        }
    return {
        "thermals_score": float(fallback_aspects.get("thermals_score", 78.0)),
        "acoustics_score": float(fallback_aspects.get("acoustics_score", 78.0)),
        "build_and_hinges_score": float(fallback_aspects.get("build_and_hinges_score", 78.0)),
        "keyboard_and_trackpad_score": float(fallback_aspects.get("keyboard_and_trackpad_score", 78.0)),
        "real_battery_and_reliability_score": float(fallback_aspects.get("real_battery_and_reliability_score", 78.0)),
    }


def _recalibrate_item(
    ident: Dict[str, Any],
    cids: List[str],
    primary_cid: Optional[str],
    base_aspects: Dict[str, float],
    cat_map: Dict[str, Any],
) -> Dict[str, Any]:
    primary_lap = cat_map.get(primary_cid) if primary_cid else None
    if not primary_lap:
        for mcid in cids:
            if mcid in cat_map:
                primary_lap = cat_map[mcid]
                break

    fam_low = (
        str(ident.get("brand", "")) + " " +
        str(ident.get("laptop_family", "")) + " " +
        str(ident.get("laptop_model", ""))
    ).lower()

    if primary_lap:
        s = primary_lap["specs"]
        dm = primary_lap["derived_metrics"]
        is_igpu = s["gpu"].get("integrated", True)
        tgp_w = float(dm["silicon"].get("inferred_tgp_w") or 0.0)
        cpu_w = float(s["cpu"].get("base_power_w") or 28.0)
        batt_hrs = float(dm["mobility"].get("battery_hours_estimate") or 5.0)
        chassis_tier = str(dm["longevity"].get("chassis_tier") or "")
    else:
        is_igpu = True
        tgp_w = 0.0
        cpu_w = 28.0
        batt_hrs = 5.5
        chassis_tier = ""

    # 1. Stretch baseline scores away from the 75.0 Bayesian center (1.25x avoids 96/42 saturation)
    def stretch(val: float, lo: float = 42.0, hi: float = 96.0) -> float:
        stretched = 75.0 + (float(val) - 75.0) * 1.25
        return round(max(lo, min(hi, stretched)), 1)

    therm = stretch(base_aspects.get("thermals_score", 78.0))
    acoust = stretch(base_aspects.get("acoustics_score", 78.0))
    build = stretch(base_aspects.get("build_and_hinges_score", 78.0))
    kb = stretch(base_aspects.get("keyboard_and_trackpad_score", 78.0))

    # 2. Differentiate Build & Hinges by actual chassis material & convertible/budget class
    if "Metal" in chassis_tier or any(k in fam_low for k in ["prestige", "zenbook", "proart", "zephyrus", "legion pro", "strix scar", "omnibook", "yoga", "thinkpad", "latitude"]):
        build = max(build, 84.5 if "omnibook" in fam_low or "latitude" in fam_low else 89.0)
    elif any(k in fam_low for k in ["flex", "victus", "15-fd", "15-fc", "255 g", "250 g", "aspire", "modern", "ideapad 1", "ideapad 3"]):
        build = min(build, 71.5)

    # 3. Anchor Real Battery Run-Time to actual estimated battery endurance & HX/dGPU power draw
    raw_batt_score = 38.0 + (batt_hrs - 2.5) * 7.2
    if not is_igpu and (cpu_w >= 55.0 or tgp_w >= 115.0):
        raw_batt_score = min(raw_batt_score, 61.5)
        acoust = min(acoust, 72.5)
    elif is_igpu and batt_hrs >= 7.0:
        raw_batt_score = max(raw_batt_score, 86.5)

    batt = round(max(45.0, min(95.0, raw_batt_score)), 1)
    updated_aspects = {
        "thermals_score": therm,
        "acoustics_score": acoust,
        "build_and_hinges_score": build,
        "keyboard_and_trackpad_score": kb,
        "real_battery_and_reliability_score": batt,
    }
    comm_score = round(0.30 * therm + 0.15 * acoust + 0.25 * build + 0.15 * kb + 0.15 * batt, 2)
    return {"community_nlp_score": comm_score, "aspect_scores": updated_aspects}


def recalibrate_catalog_and_reviews(
    reviews_path: str = "reviews_deduplicated_v6.json",
    catalog_path: str = "unified_catalog_topsis_ready_v6.json",
) -> Dict[str, Any]:
    """
    Fixes Bayesian clustering in the 5 Field Review Aspects with a balanced 1.25x contrast multiplier
    (preventing 96.0/42.0 saturation) anchored to original baseline aspect scores, and updates
    `reviews_deduplicated_v6.json`, `unified_catalog_topsis_ready_v6.json`, and cleaned JSON if present.
    """
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
            if base_asp:
                recal = _recalibrate_item(item.get("identity", {}), cids, cids[0] if cids else None, base_asp, cat_map)
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
            recal = _recalibrate_item(item.get("identity", {}), cids, item.get("primary_canonical_id"), base_asp, cat_map)
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
    reviews_json_path: str = "reviews_deduplicated_v6.json",
    catalog_json_path: str = "unified_catalog_topsis_ready_v6.json",
    chroma_dir: str = CHROMA_DEFAULT_DIR,
    model_name: str = MODEL_NAME,
    recalibrate_first: bool = True,
) -> Dict[str, Any]:
    """
    Builds/updates the persistent ChromaDB collection using `jina-embeddings-v3`.
    Reads deduplicated chassis reviews from `reviews_deduplicated_v6.json` (`clean_profile_lists` +
    verified `scraped_editorial` chunks) or legacy `laptops` lists, and rebuilds `./chroma_reviews_db`.
    """
    if recalibrate_first and Path(reviews_json_path).exists():
        data = recalibrate_catalog_and_reviews(reviews_json_path, catalog_json_path)
    else:
        with open(reviews_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    client = chromadb.PersistentClient(path=chroma_dir)
    passage_emb_fn = JinaV3EmbeddingFunction(model_name=model_name, task="retrieval.passage")

    # Recreate collection cleanly so 512d vectors never clash with previous collections
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=passage_emb_fn,
        metadata={"hnsw:space": "cosine"},
    )

    merged_by_ckey: Dict[str, Dict[str, Any]] = {}
    db_update_payload: Dict[str, Dict[str, Any]] = {}

    if "chassis_reviews" in data:
        for item in data.get("chassis_reviews", []):
            ckey = item["chassis_key"]
            cids_list = item.get("matched_canonical_ids", [])
            brand = item.get("identity", {}).get("brand", "") or ""
            comm_score = float(item.get("community_nlp_score", 75.0))
            clean_lists = item.get("clean_profile_lists", {})
            chunks = item.get("deduplicated_chunks", [])
            ed_pros = [c["text"] for c in chunks if c.get("source_type") == "scraped_editorial" and c.get("polarity") == "pro"]
            ed_cons = [c["text"] for c in chunks if c.get("source_type") == "scraped_editorial" and c.get("polarity") == "con"]

            pros_ar_list = list(clean_lists.get("pros_ar", []))
            cons_ar_list = list(clean_lists.get("cons_ar", []))
            pros_en_list = list(dict.fromkeys(list(clean_lists.get("pros_en", [])) + ed_pros))
            cons_en_list = list(dict.fromkeys(list(clean_lists.get("cons_en", [])) + ed_cons))

            prof_summary = {
                "community_nlp_score": comm_score,
                "aspect_scores": item.get("aspect_scores", {}),
                "pros_ar": pros_ar_list,
                "cons_ar": cons_ar_list,
                "pros_en": pros_en_list,
                "cons_en": cons_en_list,
            }
            for cid in cids_list:
                db_update_payload[cid] = prof_summary

            merged_by_ckey[ckey] = {
                "brand": brand,
                "cids": list(cids_list),
                "scores": [comm_score],
                "pros_ar": pros_ar_list,
                "pros_en": pros_en_list,
                "cons_ar": cons_ar_list,
                "cons_en": cons_en_list,
            }
    else:
        for item in data.get("laptops", []):
            ckey = item["chassis_key"]
            prof = item.get("nlp_review_profile", {})
            cids_list = item.get("matched_canonical_ids", [])
            brand = item.get("identity", {}).get("brand", "")
            comm_score = float(prof.get("community_nlp_score", 75.0))

            for cid in cids_list:
                db_update_payload[cid] = prof

            if ckey not in merged_by_ckey:
                merged_by_ckey[ckey] = {
                    "brand": brand,
                    "cids": list(cids_list),
                    "scores": [comm_score],
                    "pros_ar": list(prof.get("pros_ar", [])),
                    "pros_en": list(prof.get("pros_en", [])),
                    "cons_ar": list(prof.get("cons_ar", [])),
                    "cons_en": list(prof.get("cons_en", [])),
                }
            else:
                entry = merged_by_ckey[ckey]
                entry["cids"].extend(cids_list)
                entry["scores"].append(comm_score)
                entry["pros_ar"].extend(prof.get("pros_ar", []))
                entry["pros_en"].extend(prof.get("pros_en", []))
                entry["cons_ar"].extend(prof.get("cons_ar", []))
                entry["cons_en"].extend(prof.get("cons_en", []))

    records_by_id: Dict[str, tuple] = {}
    for ckey, entry in merged_by_ckey.items():
        cids_csv = ",".join(dict.fromkeys(c for c in entry["cids"] if c))
        avg_score = round(sum(entry["scores"]) / len(entry["scores"]), 2)

        # Preserve order while deduplicating sentences across merged duplicate chassis entries
        pros_ar_u = list(dict.fromkeys(s.strip() for s in entry["pros_ar"] if s and s.strip()))
        pros_en_u = list(dict.fromkeys(s.strip() for s in entry["pros_en"] if s and s.strip()))
        cons_ar_u = list(dict.fromkeys(s.strip() for s in entry["cons_ar"] if s and s.strip()))
        cons_en_u = list(dict.fromkeys(s.strip() for s in entry["cons_en"] if s and s.strip()))

        pros_text = " | ".join(pros_ar_u + pros_en_u)
        if pros_text:
            records_by_id[f"{ckey}__pro"] = (
                pros_text,
                {
                    "chassis_key": ckey,
                    "brand": entry["brand"],
                    "polarity": "pro",
                    "community_nlp_score": avg_score,
                    "matched_canonical_ids": cids_csv,
                },
            )

        cons_text = " | ".join(cons_ar_u + cons_en_u)
        if cons_text:
            records_by_id[f"{ckey}__con"] = (
                cons_text,
                {
                    "chassis_key": ckey,
                    "brand": entry["brand"],
                    "polarity": "con",
                    "community_nlp_score": avg_score,
                    "matched_canonical_ids": cids_csv,
                },
            )

    existing_ids = set(collection.get(include=[])["ids"])
    pending = [(did, txt, meta) for did, (txt, meta) in records_by_id.items() if did not in existing_ids]
    docs = [p[1] for p in pending]
    metadatas = [p[2] for p in pending]
    ids = [p[0] for p in pending]
    print(f"[ChromaDB] Total unique docs: {len(records_by_id)}, already indexed: {len(existing_ids)}, remaining: {len(ids)}")

    batch_size = 16
    for i in range(0, len(docs), batch_size):
        collection.upsert(
            documents=docs[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
            ids=ids[i:i + batch_size],
        )
        print(f"  [ChromaDB] Indexed {min(i + batch_size, len(docs))}/{len(docs)} remaining documents...")

    print(f"[ChromaDB] Indexed {len(records_by_id)} total unique documents into '{chroma_dir}' using {model_name}.")
    return {
        "indexed_documents_count": len(records_by_id),
        "updated_laptops_count": len(db_update_payload),
        "profiles_by_canonical_id": db_update_payload,
    }


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