"""Infrastructure loader for optional local fallback catalog & review snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def extract_review_profiles_from_payload(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build a `{canonical_id: review_profile}` lookup from Format B1 or B2 payloads."""
    lookup: Dict[str, Dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return lookup

    if isinstance(payload.get("chassis_reviews"), list):
        for entry in payload["chassis_reviews"]:
            if not isinstance(entry, dict):
                continue
            clean_lists = entry.get("clean_profile_lists", {})
            chunks = entry.get("deduplicated_chunks", [])
            ed_pros = [
                c["text"]
                for c in chunks
                if c.get("source_type") == "scraped_editorial" and c.get("polarity") == "pro"
            ]
            ed_cons = [
                c["text"]
                for c in chunks
                if c.get("source_type") == "scraped_editorial" and c.get("polarity") == "con"
            ]
            profile = {
                "community_nlp_score": float(entry.get("community_nlp_score", 75.0)),
                "aspect_scores": dict(entry.get("aspect_scores", {})),
                "pros_ar": list(clean_lists.get("pros_ar", [])),
                "cons_ar": list(clean_lists.get("cons_ar", [])),
                "pros_en": list(dict.fromkeys(list(clean_lists.get("pros_en", [])) + ed_pros)),
                "cons_en": list(dict.fromkeys(list(clean_lists.get("cons_en", [])) + ed_cons)),
            }
            cids = list(entry.get("matched_canonical_ids") or [])
            for fb in (entry.get("primary_canonical_id"), entry.get("canonical_id")):
                if fb and fb not in cids:
                    cids.append(fb)
            for cid in cids:
                if cid:
                    lookup[str(cid)] = profile
    elif isinstance(payload.get("laptops"), list):
        for entry in payload["laptops"]:
            if not isinstance(entry, dict):
                continue
            prof = entry.get("nlp_review_profile")
            if not isinstance(prof, dict) or not prof:
                continue
            cids = list(entry.get("matched_canonical_ids") or [])
            for fb in (entry.get("primary_canonical_id"), entry.get("canonical_id")):
                if fb and fb not in cids:
                    cids.append(fb)
            for cid in cids:
                if cid:
                    lookup[str(cid)] = dict(prof)

    return lookup


def load_fallback_catalog(catalog_path: str) -> List[Dict[str, Any]]:
    """Read optional local catalog JSON snapshot if present on disk."""
    cpath = Path(catalog_path)
    if not cpath.exists():
        return []
    with open(cpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("laptops", [])) if isinstance(data, dict) else []


def load_fallback_reviews_lookup(reviews_path: str) -> Dict[str, Dict[str, Any]]:
    """Read optional local reviews JSON snapshot if present on disk."""
    rpath = Path(reviews_path)
    if not rpath.exists():
        return {}
    with open(rpath, "r", encoding="utf-8") as f:
        rev_json = json.load(f)
    return extract_review_profiles_from_payload(rev_json)
