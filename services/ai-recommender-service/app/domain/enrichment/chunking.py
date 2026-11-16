"""Pure chunking, noise filtering, catalog summary and delta-hash domain logic."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from app.domain.enrichment.models import (
    _ASPECT_KEYWORDS,
    _CODE_BLOCK_RE,
    _DESKTOP_PART_RE,
    _DETAILS_BLOCK_RE,
    _HTML_TAG_RE,
    _HW_UNIT_RE,
    _LAPTOP_CONTEXT_RE,
    _NOISE_PATTERNS,
    _URL_RE,
    ENRICHER_SCHEMA_VERSION,
)
from app.domain.enrichment.scoring import is_valid_nlp_profile
from app.domain.reviews.source_filter import (
    is_relevant_community_post,
    is_relevant_editorial_review,
    is_relevant_youtube_video,
)


def _clean_text(text: str) -> str:
    """Remove HTML details blocks, markdown code dumps, URLs, and extra whitespace."""
    if not text:
        return ""
    s = _DETAILS_BLOCK_RE.sub(" ", text)
    s = _CODE_BLOCK_RE.sub(" ", s)
    s = _HTML_TAG_RE.sub(" ", s)
    s = _URL_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _split_clean_chunks(text: str, word_chunk_size: int = 32) -> List[str]:
    """
    Split text into sentence/phrase chunks. For unpunctuated YouTube auto-captions
    (>45 words without terminal punctuation), slice cleanly into overlapping-free
    `word_chunk_size`-word windows.
    """
    cleaned = _clean_text(text)
    if not cleaned:
        return []

    raw_parts = [p.strip() for p in re.split(r"(?<=[.!?؟])\s+|\n+", cleaned) if p.strip()]
    out: List[str] = []
    for part in raw_parts:
        words = part.split()
        if len(words) < 6:
            continue
        if len(words) > 45:
            for i in range(0, len(words), word_chunk_size):
                seg = " ".join(words[i : i + word_chunk_size]).strip()
                if len(seg.split()) >= 6 and len(seg) >= 25:
                    out.append(seg[:360])
        elif len(part) >= 25:
            out.append(part[:360])
    return out


def _is_noisy_or_offtopic(chunk: str, post_title: str = "", ident: Optional[Dict[str, Any]] = None) -> bool:
    """Filter sponsor plugs, beginner questions, driver dumps, and mismatched desktop-part reviews."""
    if _NOISE_PATTERNS.search(chunk) or (post_title and _NOISE_PATTERNS.search(post_title)):
        return True

    combined = f"{post_title} {chunk}"
    if _DESKTOP_PART_RE.search(combined) and not _LAPTOP_CONTEXT_RE.search(combined):
        return True

    # Filter obvious mismatched product editorial titles (e.g. Alienware editorial attached to ASUS)
    if post_title and ident:
        brand = str(ident.get("brand") or "").strip().lower()
        t_low = post_title.lower()
        other_brands = {"alienware", "apple", "macbook", "gigabyte", "razer", "samsung"} - {brand}
        if brand and brand not in t_low:
            if any(re.search(rf"\b{re.escape(ob)}\b", t_low) for ob in other_brands):
                # Allow comparative sentences inside transcripts, reject mismatched article/post titles
                if not re.search(rf"\b{re.escape(brand)}\b", chunk.lower()):
                    return True
    return False


def _gather_raw_candidate_chunks(
    item: Dict[str, Any],
    screen_size: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Extract cleaned candidate chunks from YouTube transcripts, top comments, and community posts.
    Returns `(candidates, raw_evidence_doc_count)`.
    """
    ident = item.get("identity") or {}
    candidates: List[Dict[str, Any]] = []
    doc_count = 0

    yt = item.get("youtube") or {}
    for vid in yt.get("videos", []):
        if not isinstance(vid, dict):
            continue
        if not is_relevant_youtube_video(vid, ident, screen_size=screen_size)[0]:
            continue
        src_tag = str(vid.get("transcript_source") or vid.get("status") or "").strip()
        transcript = str(vid.get("transcript_text") or "").strip()
        vid_title = str(vid.get("title") or "").strip()
        channel = str(vid.get("channel_name") or "YouTube").strip()
        if (
            transcript
            and src_tag not in ("TRANSCRIPT_UNAVAILABLE", "TRANSCRIPT_ERROR")
            and not transcript.startswith("[Synthesized from")
            and not transcript.startswith("[TRANSCRIPT")
        ):
            doc_count += 1
            for seg in _split_clean_chunks(transcript, word_chunk_size=32)[:65]:
                if not _is_noisy_or_offtopic(seg, vid_title, ident):
                    candidates.append(
                        {
                            "text": seg,
                            "source": f"YT:{channel}",
                            "source_weight": 1.15,
                        }
                    )

        for cmt in vid.get("top_comments", []):
            if not isinstance(cmt, dict):
                continue
            ctext = str(cmt.get("comment_text") or "").strip()
            if not ctext:
                continue
            if ctext.rstrip().endswith("?") and len(ctext) < 140:
                continue
            for seg in _split_clean_chunks(ctext, word_chunk_size=32)[:5]:
                if not _is_noisy_or_offtopic(seg, vid_title, ident):
                    likes = int(cmt.get("like_count") or 0)
                    candidates.append(
                        {
                            "text": seg,
                            "source": "YT_Comment",
                            "source_weight": 0.95 + min(0.20, likes * 0.01),
                        }
                    )

    comm = item.get("communities") or {}
    for bucket_name, posts in comm.items():
        if not isinstance(posts, list):
            continue
        for post in posts:
            if not isinstance(post, dict):
                continue

            # Editorial reviews use pros/cons/verdict/review_url instead of post_title/post_body.
            is_editorial = bucket_name == "editorial" or any(
                key in post for key in ("verdict", "pros", "cons", "review_url")
            )
            if is_editorial:
                if not is_relevant_editorial_review(post, ident, screen_size=screen_size)[0]:
                    continue
                ed_title = str(post.get("source") or post.get("post_title") or "Editorial").strip()
                ed_parts: List[str] = []
                for p in post.get("pros") or []:
                    if isinstance(p, str) and p.strip():
                        ed_parts.append(p.strip())
                for c in post.get("cons") or []:
                    if isinstance(c, str) and c.strip():
                        ed_parts.append(c.strip())
                verdict = str(post.get("verdict") or "").strip()
                if verdict:
                    ed_parts.append(verdict)
                ed_segs = [
                    s
                    for part in ed_parts
                    for s in _split_clean_chunks(part, word_chunk_size=32)[:10]
                    if not _is_noisy_or_offtopic(s, ed_title, ident)
                ]
                if ed_segs:
                    doc_count += 1
                    review_src = str(post.get("source") or bucket_name).strip()
                    for seg in ed_segs:
                        candidates.append(
                            {
                                "text": seg,
                                "source": f"Comm:editorial:{review_src}",
                                "source_weight": 1.1,
                            }
                        )
                continue

            if not is_relevant_community_post(post, ident, screen_size=screen_size)[0]:
                continue

            ptitle = str(post.get("post_title") or post.get("title") or post.get("headline") or "").strip()
            pbody = str(
                post.get("post_body")
                or post.get("selftext")
                or post.get("body")
                or post.get("text")
                or post.get("content")
                or post.get("article_body")
                or ""
            ).strip()
            if not (ptitle or pbody):
                continue
            if ptitle and _DESKTOP_PART_RE.search(ptitle) and not _LAPTOP_CONTEXT_RE.search(ptitle):
                continue
            combined = f"{ptitle}. {pbody}".strip(". ")
            segs = [s for s in _split_clean_chunks(combined, word_chunk_size=32)[:25] if not _is_noisy_or_offtopic(s, ptitle, ident)]
            if segs:
                doc_count += 1
                plat = str(post.get("platform") or bucket_name).strip()
                for seg in segs:
                    candidates.append(
                        {
                            "text": seg,
                            "source": f"Comm:{plat}",
                            "source_weight": 1.0,
                        }
                    )
            for cmt in post.get("comments", []) or []:
                ctext = str(
                    cmt.get("comment_text") or cmt.get("body") or cmt.get("text") or ""
                    if isinstance(cmt, dict)
                    else cmt
                ).strip()
                if ctext and not ctext.rstrip().endswith("?"):
                    for seg in _split_clean_chunks(ctext, word_chunk_size=32)[:4]:
                        if not _is_noisy_or_offtopic(seg, ptitle, ident):
                            candidates.append(
                                {
                                    "text": seg,
                                    "source": f"Comm_Cmt:{bucket_name}",
                                    "source_weight": 0.9,
                                }
                            )

    return candidates, doc_count


def _format_catalog_specs_summary(item: Dict[str, Any], cat_map: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract compact grounded catalog hardware specs for prompt & fallback grounding."""
    ident = item.get("identity") or {}
    cids = list(item.get("matched_canonical_ids") or [])
    primary_cid = item.get("primary_canonical_id") or (cids[0] if cids else None)
    cat_entry = None
    if cat_map:
        if primary_cid and primary_cid in cat_map:
            cat_entry = cat_map[primary_cid]
        else:
            for cid in cids:
                if cid in cat_map:
                    cat_entry = cat_map[cid]
                    break

    item_specs = item.get("specs") if isinstance(item.get("specs"), dict) else {}
    specs = (cat_entry or {}).get("specs") or item_specs
    dm = (
        (cat_entry or {}).get("derived_metrics")
        or (item.get("derived_metrics") if isinstance(item.get("derived_metrics"), dict) else None)
        or (item_specs.get("derived_metrics") if isinstance(item_specs.get("derived_metrics"), dict) else None)
        or {}
    )
    cpu = specs.get("cpu") or {}
    gpu = specs.get("gpu") or {}
    mem = specs.get("memory") or {}
    disp = specs.get("display") or {}
    stor = specs.get("storage") or {}
    longevity = dm.get("longevity") or {}
    mobility = dm.get("mobility") or {}

    return {
        "brand": ident.get("brand") or (cat_entry or {}).get("brand") or "",
        "laptop_family": ident.get("laptop_family") or (cat_entry or {}).get("laptop_family") or "",
        "laptop_model": ident.get("laptop_model") or (cat_entry or {}).get("laptop_model") or "",
        "category": (specs.get("identity") or {}).get("primary_category") or "",
        "cpu": cpu.get("raw") or cpu.get("model") or "",
        "gpu": gpu.get("raw") or gpu.get("model") or "",
        "gpu_tgp_w": gpu.get("tgp_watts"),
        "ram_gb": mem.get("capacity_gb"),
        "ram_upgradeable": mem.get("upgradeable"),
        "storage_gb": stor.get("capacity_gb"),
        "display_size_in": disp.get("size_inches"),
        "display_panel": disp.get("panel_type"),
        "display_hz": disp.get("refresh_rate_hz"),
        "display_nits": disp.get("brightness_nits"),
        "display_srgb_pct": disp.get("srgb_percent"),
        "battery_whr": mobility.get("battery_whr") or (specs.get("battery") or {}).get("capacity_whr"),
        "weight_kg": mobility.get("weight_kg"),
        "chassis_material": longevity.get("chassis_material"),
        "verified_metal_chassis": longevity.get("verified_metal_chassis"),
        "cooling_system": (specs.get("thermals") or {}).get("cooling_description") or "",
    }


def _select_top_candidates_for_jina(
    candidates: List[Dict[str, Any]],
    max_candidates: int = 24,
) -> List[Dict[str, Any]]:
    """
    Deduplicate candidates, cap each text at 220 chars, score lexically for hardware/aspect
    signals + source reliability + summary position, and select a diverse set of up to
    `max_candidates` covering transcripts (head/mid/tail), comments, and communities.
    """
    seen_lower = set()
    unique_cands: List[Dict[str, Any]] = []
    for c in candidates:
        trimmed = str(c.get("text") or "")[:220].strip()
        if len(trimmed) < 20:
            continue
        norm = re.sub(r"\s+", " ", trimmed.lower()).strip()
        if norm in seen_lower:
            continue
        seen_lower.add(norm)
        entry = dict(c)
        entry["text"] = trimmed
        unique_cands.append(entry)

    n = len(unique_cands)
    if n <= max_candidates:
        return unique_cands

    kw_terms = tuple(
        tok
        for asp in _ASPECT_KEYWORDS.values()
        for pol in ("pro", "con")
        for tok in asp[pol]
    )

    scored: List[Tuple[float, int, Dict[str, Any]]] = []
    tail_cutoff = int(n * 0.75)
    for idx, c in enumerate(unique_cands):
        txt = c["text"]
        tlow = txt.lower()
        kw_hits = len(_HW_UNIT_RE.findall(txt)) + sum(1 for kw in kw_terms if kw in tlow)
        pos_bonus = 0.5 if idx >= tail_cutoff else 0.0
        src_bonus = 0.35 if str(c.get("source") or "").startswith(("YT_Comment", "Comm:")) else 0.0
        lex_score = kw_hits * 1.2 + float(c.get("source_weight") or 1.0) + pos_bonus + src_bonus
        scored.append((lex_score, idx, c))

    picked_idx = set()
    selected: List[Dict[str, Any]] = []

    def _add(orig_idx: int, cand_obj: Dict[str, Any]) -> None:
        if orig_idx not in picked_idx and len(selected) < max_candidates:
            picked_idx.add(orig_idx)
            selected.append(cand_obj)

    # Seed diversity across head, middle, tail, and community/comment buckets
    buckets = [
        [x for x in scored if x[1] < n // 3],
        [x for x in scored if n // 3 <= x[1] < (2 * n) // 3],
        [x for x in scored if x[1] >= (2 * n) // 3],
    ]
    per_bucket = max(4, max_candidates // 6)
    for bkt in buckets:
        bkt_sorted = sorted(bkt, key=lambda x: x[0], reverse=True)
        for _, orig_idx, cand_obj in bkt_sorted[:per_bucket]:
            _add(orig_idx, cand_obj)

    # Fill remainder with top overall lexical-weighted candidates
    for _, orig_idx, cand_obj in sorted(scored, key=lambda x: x[0], reverse=True):
        if len(selected) >= max_candidates:
            break
        _add(orig_idx, cand_obj)

    return selected


def detect_reviews_format(payload: Any) -> str:
    """
    Auto-detect review dataset schema:
    - 'format_b2_deduplicated': `chassis_reviews[]` payload from review deduplication
    - 'format_b1_enriched': `laptops[]` where items already carry valid `nlp_review_profile`
    - 'format_a_raw': `laptops[]` raw scraper output lacking valid `nlp_review_profile`
    """
    if not isinstance(payload, dict):
        raise ValueError("Reviews payload must be a JSON object.")

    if isinstance(payload.get("chassis_reviews"), list):
        return "format_b2_deduplicated"

    laptops = payload.get("laptops")
    if isinstance(laptops, list):
        valid_count = sum(
            1 for item in laptops if isinstance(item, dict) and is_valid_nlp_profile(item.get("nlp_review_profile"))
        )
        if valid_count > 0:
            return "format_b1_enriched"
        return "format_a_raw"

    raise ValueError(
        "Unrecognized reviews payload schema: expected 'chassis_reviews' (Format B2) "
        "or 'laptops' (Format A / Format B1)."
    )


def count_missing_profiles(payload: Dict[str, Any]) -> int:
    """Count Format A/B1 laptop chassis entries missing a valid `nlp_review_profile`."""
    return sum(
        1
        for item in payload.get("laptops", [])
        if isinstance(item, dict) and not is_valid_nlp_profile(item.get("nlp_review_profile"))
    )


def compute_chassis_delta_hash(
    item: Dict[str, Any],
    cat_map: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Compute deterministic SHA-256 hash of a chassis's raw scraped evidence + catalog identity/specs
    so unchanged chassis do not re-trigger remote LLM enrichment.
    """
    specs = _format_catalog_specs_summary(item, cat_map)
    yt_videos = []
    for v in (item.get("youtube") or {}).get("videos", []):
        if not isinstance(v, dict):
            continue
        yt_videos.append(
            {
                "video_id": v.get("video_id") or "",
                "transcript_source": v.get("transcript_source") or "",
                "transcript_hash": hashlib.sha256(
                    str(v.get("transcript_text") or "").encode("utf-8")
                ).hexdigest(),
                "comments": [
                    str(c.get("comment_text") or "")
                    for c in (v.get("top_comments") or [])
                    if isinstance(c, dict)
                ],
            }
        )
    yt_videos.sort(key=lambda x: x["video_id"])

    comm_items = []
    for bname, posts in sorted((item.get("communities") or {}).items()):
        if not isinstance(posts, list):
            continue
        for p in posts:
            if not isinstance(p, dict):
                continue
            raw_body = (
                p.get("post_body")
                or p.get("body")
                or p.get("text")
                or p.get("verdict")
                or ""
            )
            pros_cons = " | ".join(
                str(x) for x in ([*(p.get("pros") or []), *(p.get("cons") or [])]) if x
            )
            combined_body = f"{raw_body}\n{pros_cons}".strip()
            comm_items.append(
                {
                    "bucket": bname,
                    "post_id": str(p.get("post_id") or p.get("post_url") or p.get("review_url") or ""),
                    "title": str(p.get("post_title") or p.get("title") or p.get("source") or ""),
                    "body_hash": hashlib.sha256(combined_body.encode("utf-8")).hexdigest(),
                }
            )
    comm_items.sort(key=lambda x: (x["bucket"], x["post_id"], x["body_hash"]))

    canonical_blob = {
        "schema_version": ENRICHER_SCHEMA_VERSION,
        "chassis_key": item.get("chassis_key") or "",
        "specs": specs,
        "youtube": yt_videos,
        "communities": comm_items,
    }
    encoded = json.dumps(canonical_blob, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
