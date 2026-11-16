"""Pure domain review deduplication, aspect tagging, and catalog coverage audit logic.

Zero file I/O, zero NumPy, zero database or framework imports: operates strictly on
in-memory Python mappings so it can be unit-tested in isolation in milliseconds.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

ASPECT_KEYWORDS: Dict[str, List[str]] = {
    "thermals": [
        "thermal", "thermals", "cooling", "cool", "heat", "heatpipe", "fan", "fans",
        "temp", "temperature", "temperatures", "warm", "hot", "overheat", "throttl",
        "noise", "loud", "quiet", "acoustic", "db",
        "تبريد", "حرارة", "سخونة", "يسخن", "مراوح", "مروحة", "أنابيب", "اختناق", "صوت", "هادي", "هادئ", "دوشة",
    ],
    "battery": [
        "battery", "wh", "hour", "hours", "drain", "drains", "charging", "charger",
        "endurance", "plug", "ac adapter", "unplugged", "usb-c pd",
        "بطارية", "البطارية", "شحن", "ساعات", "ساعة", "بتخلص", "شاحن",
    ],
    "screen": [
        "display", "screen", "panel", "oled", "ips", "tn", "va", "srgb", "ntsc",
        "dci-p3", "nits", "bright", "brightness", "dim", "hz", "refresh", "color",
        "colors", "glare", "resolution", "fhd", "qhd", "2.8k", "3k",
        "شاشة", "الشاشة", "ألوان", "الوان", "سطوع", "أوليد", "اوليد", "تردد", "دقة", "إضاءة",
    ],
    "build_quality": [
        "build", "chassis", "hinge", "hinges", "wobble", "flex", "metal", "aluminum",
        "aluminium", "magnesium", "plastic", "mil-std", "durable", "durability", "lid",
        "keyboard", "trackpad", "touchpad", "weight", "kg", "heavy", "lightweight",
        "شاسيه", "هيكل", "مفصلات", "المفصلات", "تهتز", "اهتزاز", "معدن", "معدني", "بلاستيك",
        "متين", "متانة", "خامات", "كيبورد", "تاتش باد", "وزن", "خفيف", "ثقيل",
    ],
    "performance": [
        "performance", "cpu", "gpu", "rtx", "gtx", "arc", "radeon", "ryzen", "core i",
        "ultra", "snapdragon", "fps", "frame", "gaming", "render", "ram", "ddr4",
        "ddr5", "lpddr5", "ssd", "m.2", "nvme", "tgp", "watt", "upgrade", "upgradeable",
        "أداء", "اداء", "معالج", "بروسيسور", "كارت", "فريمات", "ألعاب", "العاب", "رندر",
        "رام", "رامات", "تخزين", "هارد", "تطوير", "ترقية", "ملحومة",
    ],
}

CRITICAL_ASPECTS: List[str] = ["thermals", "battery", "screen", "build_quality"]

CON_SIGNAL_KEYWORDS: List[str] = [
    "con", "cons", "issue", "issues", "problem", "problems", "flaw", "weak", "poor",
    "bad", "worst", "disappoint", "wobble", "flex", "dim", "muddy", "45% ntsc",
    "loud", "noise", "noisy", "hot", "overheat", "warm", "throttle", "drain", "short battery",
    "soldered", "not upgradeable", "limited", "plastic", "heavy", "bulky", "no ethernet",
    "no thunderbolt", "power limit", "lacking", "wish", "average", "mediocre",
    "عيب", "عيوب", "مشكلة", "مشاكل", "ضعيف", "ضعيفة", "تهتز", "اهتزاز", "سطوع منخفض",
    "يسخن", "سخونة", "مرتفعة", "مرتفع", "مزعج", "صوت المراوح", "بتخلص", "قصيرة",
    "ملحومة", "غير قابلة", "بلاستيك", "ثقيل", "تقييد", "باهتة",
]

PRO_SIGNAL_KEYWORDS: List[str] = [
    "pro", "pros", "great", "excellent", "solid", "strong", "good", "best", "impressive",
    "amazing", "bright", "accurate", "100% srgb", "dci-p3", "oled", "quiet", "cool",
    "durable", "metal", "aluminum", "mil-std", "lightweight", "upgradeable", "smooth",
    "snappy", "comfortable", "fast", "all-day", "long battery",
    "ممتاز", "ممتازة", "قوي", "قوية", "جيد", "جيدة", "رائع", "متين", "متينة", "معدني",
    "خفيف", "هادئ", "دقيقة", "سطوع عالي", "أوليد", "تطوير", "مريح", "مريحة", "سريع",
]

ASPECT_LABELS_EN: Dict[str, str] = {
    "thermals": "Thermals",
    "battery": "Battery",
    "screen": "Screen",
    "build_quality": "Build/Hinges",
}

ASPECT_LABELS_AR: Dict[str, str] = {
    "thermals": "تبريد وحرارة",
    "battery": "بطارية",
    "screen": "شاشة",
    "build_quality": "جودة تصنيع ومفصلات",
}


def normalize_review_text(text: str) -> str:
    """Normalize whitespace and case for text matching and exact deduplication."""
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def char_word_features(text: str) -> Counter[str]:
    """Extract mixed word unigrams and 3/4-char n-grams for sparse cosine matching."""
    norm = re.sub(r"[^\w\u0600-\u06FF\s]+", " ", normalize_review_text(text))
    norm = re.sub(r"\s+", " ", norm).strip()
    feats: Counter[str] = Counter()
    for word in norm.split():
        feats[f"w:{word}"] += 1.0
    padded = f" {norm} "
    for n in (3, 4):
        for i in range(max(0, len(padded) - n + 1)):
            feats[f"c:{padded[i:i + n]}"] += 1.0
    return feats


def cosine_sim_sparse(
    a: Counter[str],
    norm_a: float,
    b: Counter[str],
    norm_b: float,
) -> float:
    """Compute cosine similarity between two pre-normed sparse feature counters."""
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(val * b[k] for k, val in a.items() if k in b)
    return dot / (norm_a * norm_b)


def dedup_chunks_cosine(
    chunks: List[Dict[str, Any]],
    threshold: float = 0.90,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Remove exact and near-duplicate chunks (cosine > threshold) within one chassis."""
    kept: List[Dict[str, Any]] = []
    kept_norms_text: Set[str] = set()
    kept_vecs: List[Tuple[Counter[str], float]] = []
    exact_removed = 0
    near_removed = 0

    for ch in chunks:
        txt = re.sub(r"\s+", " ", str(ch.get("text") or "").strip())
        if len(txt) < 8:
            continue
        norm_txt = normalize_review_text(txt)
        if norm_txt in kept_norms_text:
            exact_removed += 1
            continue

        vec = char_word_features(txt)
        v_norm = math.sqrt(sum(v * v for v in vec.values()))
        is_near = False
        for kv, kn in kept_vecs:
            if cosine_sim_sparse(vec, v_norm, kv, kn) > threshold:
                is_near = True
                break

        if is_near:
            near_removed += 1
            continue

        kept_norms_text.add(norm_txt)
        kept_vecs.append((vec, v_norm))
        kept.append({**ch, "text": txt})

    return kept, exact_removed, near_removed


def tag_review_aspects(text: str) -> List[str]:
    """Tag all hardware aspect categories mentioned in a review chunk."""
    low = normalize_review_text(text)
    return [asp for asp, kws in ASPECT_KEYWORDS.items() if any(kw in low for kw in kws)]


def infer_review_polarity(
    text: str,
    explicit_polarity: Optional[str] = None,
) -> Tuple[str, bool]:
    """Return `(polarity, is_explicit)` using keyword signals when explicit label is absent."""
    if explicit_polarity in ("pro", "con"):
        return explicit_polarity, True
    low = normalize_review_text(text)
    con_hits = sum(1 for kw in CON_SIGNAL_KEYWORDS if kw in low)
    pro_hits = sum(1 for kw in PRO_SIGNAL_KEYWORDS if kw in low)
    inferred = "con" if con_hits > pro_hits else "pro"
    return inferred, False


def split_review_sentences(text: str, max_sentences: int = 8) -> List[str]:
    """Split review prose or captions into concise chunks."""
    parts = re.split(r"(?<=[.!؟\n])\s+", str(text or "").strip())
    expanded: List[str] = []
    for part in parts:
        p_clean = re.sub(r"\s+", " ", part).strip()
        if len(p_clean) < 20:
            continue
        words = p_clean.split()
        if len(words) > 45:
            for i in range(0, len(words), 35):
                chunk = " ".join(words[i:i + 35]).strip()
                if len(chunk) >= 20:
                    expanded.append(chunk)
        else:
            expanded.append(p_clean)
    return expanded[:max_sentences]


def select_transcript_chunks(text: str, max_chunks: int = 20) -> List[str]:
    """Select hardware-relevant chunks across the full transcript rather than only the intro."""
    all_chunks = split_review_sentences(text, max_sentences=500)
    if len(all_chunks) <= max_chunks:
        return all_chunks
    scored: List[Tuple[int, int, str]] = []
    for idx, ch in enumerate(all_chunks):
        aspect_hits = len(tag_review_aspects(ch))
        low = normalize_review_text(ch)
        signal_hits = sum(1 for kw in CON_SIGNAL_KEYWORDS + PRO_SIGNAL_KEYWORDS if kw in low)
        scored.append((aspect_hits * 3 + signal_hits, idx, ch))
    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen = sorted(scored[:max_chunks], key=lambda x: x[1])
    return [c for _, _, c in chosen]


def _canonical_dict_key(value: Dict[str, Any]) -> str:
    """Deterministic hashable key for dicts lacking a canonical URL."""
    return repr(sorted((str(k), repr(v)) for k, v in value.items()))


def _collect_item_chunks(
    items: List[Dict[str, Any]],
    totals: Dict[str, int],
) -> Tuple[List[Dict[str, Any]], int, int, int, int]:
    """Gather raw scraped + synthesized profile chunks across grouped chassis entries."""
    raw_chunks: List[Dict[str, Any]] = []
    seen_ed_urls: Set[str] = set()
    seen_disc_keys: Set[str] = set()
    seen_yt_ids: Set[str] = set()
    unique_editorial_count = 0
    unique_discussion_count = 0
    unique_real_yt_count = 0
    yt_comment_count = 0

    for it in items:
        comm = it.get("communities") if isinstance(it.get("communities"), dict) else {}
        for ed in comm.get("editorial") or []:
            if not isinstance(ed, dict):
                continue
            ekey = str(ed.get("review_url") or _canonical_dict_key(ed))
            if ekey in seen_ed_urls:
                continue
            seen_ed_urls.add(ekey)
            unique_editorial_count += 1
            for p in ed.get("pros") or []:
                raw_chunks.append(
                    {
                        "text": p,
                        "polarity": "pro",
                        "polarity_explicit": True,
                        "source_type": "scraped_editorial",
                        "source_url": ed.get("review_url"),
                    }
                )
            for c in ed.get("cons") or []:
                raw_chunks.append(
                    {
                        "text": c,
                        "polarity": "con",
                        "polarity_explicit": True,
                        "source_type": "scraped_editorial",
                        "source_url": ed.get("review_url"),
                    }
                )
            if ed.get("verdict"):
                pol, is_exp = infer_review_polarity(str(ed["verdict"]))
                raw_chunks.append(
                    {
                        "text": ed["verdict"],
                        "polarity": pol,
                        "polarity_explicit": is_exp,
                        "source_type": "scraped_editorial",
                        "source_url": ed.get("review_url"),
                    }
                )

        for disc in comm.get("discussions") or []:
            if not isinstance(disc, dict):
                continue
            dkey = str(disc.get("post_url") or f"{disc.get('platform')}:{disc.get('post_id')}")
            if dkey in seen_disc_keys:
                continue
            seen_disc_keys.add(dkey)
            unique_discussion_count += 1
            combined_body = f"{disc.get('post_title', '')}. {disc.get('post_body', '')}".strip()
            for sent in split_review_sentences(combined_body, max_sentences=5):
                pol, is_exp = infer_review_polarity(sent)
                raw_chunks.append(
                    {
                        "text": sent,
                        "polarity": pol,
                        "polarity_explicit": is_exp,
                        "source_type": "scraped_discussion",
                        "source_url": disc.get("post_url"),
                    }
                )

        yt = it.get("youtube") if isinstance(it.get("youtube"), dict) else {}
        for vid in yt.get("videos") or []:
            if not isinstance(vid, dict):
                continue
            vid_id = str(vid.get("video_id") or vid.get("video_url") or vid.get("title") or "")
            if vid_id and vid_id in seen_yt_ids:
                continue
            if vid_id:
                seen_yt_ids.add(vid_id)
            tsrc = vid.get("transcript_source")
            ttext = str(vid.get("transcript_text") or "").strip()
            if tsrc == "AI_CHASSIS_SYNTHESIS_FALLBACK" or ttext.startswith("[Synthesized from"):
                totals["synthesized_yt_fallbacks_stripped"] += 1
            elif ttext and tsrc != "TRANSCRIPT_UNAVAILABLE":
                unique_real_yt_count += 1
                for sent in select_transcript_chunks(ttext, max_chunks=20):
                    pol, is_exp = infer_review_polarity(sent)
                    raw_chunks.append(
                        {
                            "text": sent,
                            "polarity": pol,
                            "polarity_explicit": is_exp,
                            "source_type": "scraped_youtube_transcript",
                            "source_url": vid.get("video_url"),
                        }
                    )

            for cm in vid.get("top_comments") or []:
                if not isinstance(cm, dict):
                    continue
                ctext = str(cm.get("comment_text") or "").strip()
                if len(ctext) >= 20:
                    yt_comment_count += 1
                    pol, is_exp = infer_review_polarity(ctext)
                    raw_chunks.append(
                        {
                            "text": ctext,
                            "polarity": pol,
                            "polarity_explicit": is_exp,
                            "source_type": "scraped_youtube_comment",
                            "source_url": vid.get("video_url"),
                        }
                    )

        prof = it.get("nlp_review_profile") if isinstance(it.get("nlp_review_profile"), dict) else {}
        for field, pol in [("pros_en", "pro"), ("pros_ar", "pro"), ("cons_en", "con"), ("cons_ar", "con")]:
            for s in prof.get(field) or []:
                raw_chunks.append(
                    {
                        "text": s,
                        "polarity": pol,
                        "polarity_explicit": True,
                        "source_type": "synthesized_profile",
                        "lang": "ar" if field.endswith("_ar") else "en",
                    }
                )

    return raw_chunks, unique_editorial_count, unique_discussion_count, unique_real_yt_count, yt_comment_count


def _clean_http_url(raw: Any) -> Optional[str]:
    """Return a normalized HTTP(S) URL or None for empty/unsafe values."""
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    low = cleaned.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return cleaned
    return None


def _coerce_optional_int(raw: Any) -> Optional[int]:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _coerce_optional_float(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        val = float(raw)
        return val if math.isfinite(val) else None
    except (TypeError, ValueError):
        return None


def _extract_compact_review_sources(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract deduplicated review URLs and metadata without heavy transcripts or bodies."""
    sources_by_url: Dict[str, Dict[str, Any]] = {}

    def _register(entry: Dict[str, Any]) -> None:
        url = _clean_http_url(entry.get("url"))
        if not url:
            return
        dedup_key = url.rstrip("/").lower()
        if dedup_key not in sources_by_url:
            sources_by_url[dedup_key] = {**entry, "url": url}

    for it in items:
        for existing in it.get("review_sources") or []:
            if isinstance(existing, dict):
                _register(
                    {
                        "source_type": str(existing.get("source_type") or "community"),
                        "platform": str(existing.get("platform") or "community"),
                        "title": str(existing.get("title") or existing.get("platform") or "Review").strip(),
                        "url": existing.get("url"),
                        "author_or_channel": existing.get("author_or_channel"),
                        "channel_url": _clean_http_url(existing.get("channel_url")),
                        "rating": _coerce_optional_float(existing.get("rating")),
                        "score_or_views": _coerce_optional_int(existing.get("score_or_views")),
                        "published_at": existing.get("published_at"),
                    }
                )

        comm = it.get("communities") if isinstance(it.get("communities"), dict) else {}
        for ed in comm.get("editorial") or []:
            if not isinstance(ed, dict):
                continue
            source_name = str(ed.get("source") or "editorial").strip()
            title = str(ed.get("verdict") or f"{source_name} Review").strip()
            _register(
                {
                    "source_type": "editorial",
                    "platform": source_name.lower(),
                    "title": title,
                    "url": ed.get("review_url"),
                    "author_or_channel": source_name,
                    "channel_url": None,
                    "rating": _coerce_optional_float(ed.get("rating")),
                    "score_or_views": None,
                    "published_at": None,
                }
            )

        yt = it.get("youtube") if isinstance(it.get("youtube"), dict) else {}
        for vid in yt.get("videos") or []:
            if not isinstance(vid, dict):
                continue
            channel_name = str(vid.get("channel_name") or "").strip() or None
            _register(
                {
                    "source_type": "youtube",
                    "platform": "youtube",
                    "title": str(vid.get("title") or channel_name or "YouTube Review").strip(),
                    "url": vid.get("video_url"),
                    "author_or_channel": channel_name,
                    "channel_url": _clean_http_url(vid.get("channel_url")),
                    "rating": None,
                    "score_or_views": _coerce_optional_int(vid.get("view_count")),
                    "published_at": vid.get("published_at"),
                }
            )

        for bucket in ("discussions", "reddit", "facebook"):
            for post in comm.get(bucket) or []:
                if not isinstance(post, dict):
                    continue
                platform = str(post.get("platform") or (bucket if bucket != "discussions" else "community")).strip()
                _register(
                    {
                        "source_type": "community",
                        "platform": platform.lower(),
                        "title": str(post.get("post_title") or post.get("title") or f"{platform} Discussion").strip(),
                        "url": post.get("post_url") or post.get("url"),
                        "author_or_channel": (str(post.get("author")).strip() if post.get("author") else None),
                        "channel_url": None,
                        "rating": None,
                        "score_or_views": _coerce_optional_int(post.get("score")),
                        "published_at": post.get("published_at"),
                    }
                )

    type_rank = {"editorial": 0, "youtube": 1, "community": 2}
    return sorted(
        sources_by_url.values(),
        key=lambda s: (
            type_rank.get(str(s.get("source_type")), 3),
            -(s.get("score_or_views") or 0),
            str(s.get("title") or ""),
        ),
    )


def _build_balance_gaps(
    scraped_doc_count: int,
    scraped_pro_cnt: int,
    scraped_con_cnt: int,
    all_pro_cnt: int,
    all_con_cnt: int,
) -> List[str]:
    gaps: List[str] = []
    if scraped_pro_cnt == 0 and all_pro_cnt < 2:
        gaps.append("Pros")
    elif scraped_doc_count > 0 and scraped_pro_cnt == 0:
        gaps.append("Scraped Pros")
    if scraped_con_cnt == 0 and all_con_cnt < 2:
        gaps.append("Cons")
    elif scraped_doc_count > 0 and scraped_con_cnt == 0:
        gaps.append("Scraped Cons")
    elif all_con_cnt < 2:
        gaps.append("Cons (<2)")
    return gaps


def audit_and_deduplicate_payload(
    reviews_data: Dict[str, Any],
    catalog_data: Optional[Dict[str, Any]] = None,
    *,
    reviews_source: str = "",
    catalog_source: str = "",
    raw_stats: Optional[Dict[str, Any]] = None,
    threshold: float = 0.90,
    include_unmatched_catalog: bool = True,
) -> Dict[str, Any]:
    """Merge duplicate chassis keys, cosine-dedup review chunks, and audit catalog gaps."""
    cat_laptops = (catalog_data or {}).get("laptops") or []
    cat_by_cid = {l["canonical_id"]: l for l in cat_laptops if isinstance(l, dict) and l.get("canonical_id")}

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    review_laptops = [it for it in (reviews_data.get("laptops") or []) if isinstance(it, dict)]
    for item in review_laptops:
        ckey = str(item.get("chassis_key") or item.get("primary_canonical_id") or item.get("canonical_id") or "")
        if ckey:
            grouped[ckey].append(item)

    all_matched_cids = {
        str(cid)
        for item in review_laptops
        for cid in (
            list(item.get("matched_canonical_ids") or [])
            + ([item["primary_canonical_id"]] if item.get("primary_canonical_id") else [])
            + ([item["canonical_id"]] if item.get("canonical_id") else [])
        )
        if cid
    }
    unmatched_cids = sorted(set(cat_by_cid.keys()) - all_matched_cids) if include_unmatched_catalog else []
    if include_unmatched_catalog:
        for ucid in unmatched_cids:
            ulap = cat_by_cid[ucid]
            brand = str(ulap.get("brand") or "Unknown").lower().replace(" ", "-")
            fam = str(ulap.get("laptop_family") or "laptop").lower().replace(" ", "-")
            mod = str(ulap.get("laptop_model") or ucid).lower().replace(" ", "-")
            synth_ckey = f"{brand}:{fam}:{mod}"
            grouped[synth_ckey].append(
                {
                    "chassis_key": synth_ckey,
                    "primary_canonical_id": ucid,
                    "matched_canonical_ids": [ucid],
                    "identity": {
                        "brand": ulap.get("brand"),
                        "laptop_family": ulap.get("laptop_family"),
                        "laptop_model": ulap.get("laptop_model") or ulap.get("title"),
                    },
                    "youtube": {"videos": []},
                    "communities": {"editorial": [], "discussions": []},
                    "nlp_review_profile": {},
                    "_synthesized_missing_from_reviews_json": True,
                }
            )

    dedup_chassis_list: List[Dict[str, Any]] = []
    totals: Dict[str, int] = {
        "raw_target_entries": len(review_laptops),
        "unique_chassis_count": len(grouped),
        "unmatched_catalog_skus_added": len(unmatched_cids),
        "input_chunks_considered": 0,
        "exact_duplicates_removed": 0,
        "near_duplicates_removed": 0,
        "synthesized_yt_fallbacks_stripped": 0,
        "kept_chunks_total": 0,
        "explicit_pro_con_chunks": 0,
        "inferred_pro_con_chunks": 0,
    }

    for ckey, items in grouped.items():
        first = items[0]
        ident = first.get("identity") if isinstance(first.get("identity"), dict) else {}
        all_item_cids = [
            str(cid)
            for it in items
            for cid in (
                list(it.get("matched_canonical_ids") or [])
                + ([it["primary_canonical_id"]] if it.get("primary_canonical_id") else [])
                + ([it["canonical_id"]] if it.get("canonical_id") else [])
            )
            if cid
        ]
        cids_ordered = list(dict.fromkeys(cid for cid in all_item_cids if cid in cat_by_cid))
        if not cids_ordered:
            cids_ordered = list(dict.fromkeys(all_item_cids))

        (
            raw_chunks,
            unique_ed_cnt,
            unique_disc_cnt,
            unique_yt_cnt,
            yt_comment_count,
        ) = _collect_item_chunks(items, totals)

        totals["input_chunks_considered"] += len(raw_chunks)
        kept_chunks, exact_rem, near_rem = dedup_chunks_cosine(raw_chunks, threshold=threshold)
        totals["exact_duplicates_removed"] += exact_rem
        totals["near_duplicates_removed"] += near_rem
        totals["kept_chunks_total"] += len(kept_chunks)

        tagged_chunks: List[Dict[str, Any]] = []
        for ch in kept_chunks:
            tagged = {**ch, "aspects": tag_review_aspects(ch["text"])}
            if tagged.get("polarity_explicit"):
                totals["explicit_pro_con_chunks"] += 1
            else:
                totals["inferred_pro_con_chunks"] += 1
            tagged_chunks.append(tagged)

        scraped_chunks = [c for c in tagged_chunks if c["source_type"] != "synthesized_profile"]
        scraped_doc_count = unique_ed_cnt + unique_disc_cnt + unique_yt_cnt

        all_pro_cnt = sum(1 for c in tagged_chunks if c["polarity"] == "pro")
        all_con_cnt = sum(1 for c in tagged_chunks if c["polarity"] == "con")
        scraped_pro_cnt = sum(1 for c in scraped_chunks if c["polarity"] == "pro")
        scraped_con_cnt = sum(1 for c in scraped_chunks if c["polarity"] == "con")

        all_aspects_covered = sorted({a for c in tagged_chunks for a in c["aspects"]})
        scraped_aspects_covered = sorted({a for c in scraped_chunks for a in c["aspects"]})
        missing_aspects_overall = [a for a in CRITICAL_ASPECTS if a not in all_aspects_covered]
        missing_aspects_scraped = [a for a in CRITICAL_ASPECTS if a not in scraped_aspects_covered]

        clean_pros_en = [c["text"] for c in tagged_chunks if c["source_type"] == "synthesized_profile" and c["polarity"] == "pro" and c.get("lang") == "en"]
        clean_pros_ar = [c["text"] for c in tagged_chunks if c["source_type"] == "synthesized_profile" and c["polarity"] == "pro" and c.get("lang") == "ar"]
        clean_cons_en = [c["text"] for c in tagged_chunks if c["source_type"] == "synthesized_profile" and c["polarity"] == "con" and c.get("lang") == "en"]
        clean_cons_ar = [c["text"] for c in tagged_chunks if c["source_type"] == "synthesized_profile" and c["polarity"] == "con" and c.get("lang") == "ar"]

        balance_gaps = _build_balance_gaps(
            scraped_doc_count=scraped_doc_count,
            scraped_pro_cnt=scraped_pro_cnt,
            scraped_con_cnt=scraped_con_cnt,
            all_pro_cnt=all_pro_cnt,
            all_con_cnt=all_con_cnt,
        )

        priority = "OK"
        if scraped_doc_count <= 1:
            priority = "High Priority"
        elif balance_gaps or missing_aspects_overall or missing_aspects_scraped:
            priority = "Medium Priority"

        display_model = ident.get("laptop_model")
        if not display_model and cids_ordered and cids_ordered[0] in cat_by_cid:
            display_model = cat_by_cid[cids_ordered[0]].get("laptop_model") or cat_by_cid[cids_ordered[0]].get("title")
        if not display_model:
            display_model = ckey

        first_prof = next(
            (
                it.get("nlp_review_profile")
                for it in items
                if isinstance(it.get("nlp_review_profile"), dict) and it.get("nlp_review_profile")
            ),
            {},
        )
        primary_cid = first.get("primary_canonical_id") or (cids_ordered[0] if cids_ordered else None)
        compact_sources = _extract_compact_review_sources(items)
        entry: Dict[str, Any] = {
            "chassis_key": ckey,
            "primary_canonical_id": primary_cid,
            "identity": {
                "brand": ident.get("brand"),
                "laptop_family": ident.get("laptop_family"),
                "laptop_model": display_model,
            },
            "sku_count_in_catalog": len(cids_ordered),
            "matched_canonical_ids": cids_ordered,
            "review_sources": compact_sources,
            "audit_metrics": {
                "scraped_doc_count": scraped_doc_count,
                "unique_editorial_count": unique_ed_cnt,
                "unique_discussion_count": unique_disc_cnt,
                "unique_real_yt_transcript_count": unique_yt_cnt,
                "yt_comments_count": yt_comment_count,
                "priority": priority,
                "kept_chunks_count": len(tagged_chunks),
                "exact_duplicates_removed": exact_rem,
                "near_duplicates_removed": near_rem,
                "all_pro_chunks": all_pro_cnt,
                "all_con_chunks": all_con_cnt,
                "scraped_pro_chunks": scraped_pro_cnt,
                "scraped_con_chunks": scraped_con_cnt,
                "balance_gaps": balance_gaps,
                "aspects_covered_overall": all_aspects_covered,
                "aspects_covered_scraped": scraped_aspects_covered,
                "missing_aspects_overall": missing_aspects_overall,
                "missing_aspects_scraped": missing_aspects_scraped,
            },
            "clean_profile_lists": {
                "pros_en": clean_pros_en,
                "pros_ar": clean_pros_ar,
                "cons_en": clean_cons_en,
                "cons_ar": clean_cons_ar,
            },
            "deduplicated_chunks": tagged_chunks,
        }
        if isinstance(first.get("specs"), dict):
            entry["specs"] = first["specs"]
        if first_prof:
            if first_prof.get("community_nlp_score") is not None:
                entry["community_nlp_score"] = first_prof["community_nlp_score"]
            if isinstance(first_prof.get("aspect_scores"), dict) and first_prof["aspect_scores"]:
                entry["aspect_scores"] = dict(first_prof["aspect_scores"])

        dedup_chassis_list.append(entry)

    zero_doc = sum(1 for c in dedup_chassis_list if c["audit_metrics"]["scraped_doc_count"] == 0)
    one_doc = sum(1 for c in dedup_chassis_list if c["audit_metrics"]["scraped_doc_count"] == 1)
    high_prio = sum(1 for c in dedup_chassis_list if c["audit_metrics"]["priority"] == "High Priority")
    med_prio = sum(1 for c in dedup_chassis_list if c["audit_metrics"]["priority"] == "Medium Priority")
    ok_prio = sum(1 for c in dedup_chassis_list if c["audit_metrics"]["priority"] == "OK")

    aspect_missing_overall_counts = {
        a: sum(1 for c in dedup_chassis_list if a in c["audit_metrics"]["missing_aspects_overall"])
        for a in CRITICAL_ASPECTS
    }
    aspect_missing_scraped_counts = {
        a: sum(1 for c in dedup_chassis_list if a in c["audit_metrics"]["missing_aspects_scraped"])
        for a in CRITICAL_ASPECTS
    }

    return {
        "audit_metadata": {
            "source_cleaned_reviews": reviews_source,
            "source_catalog": catalog_source,
            "raw_source_inspection": raw_stats or {"raw_file_found": None},
            "catalog_laptops_count": len(cat_laptops),
            "unmatched_canonical_ids": unmatched_cids,
            "deduplication_summary": {
                **totals,
                "zero_scraped_doc_chassis": zero_doc,
                "one_scraped_doc_chassis": one_doc,
                "high_priority_chassis_0_or_1_doc": high_prio,
                "medium_priority_chassis": med_prio,
                "complete_chassis": ok_prio,
                "missing_aspects_overall_counts": aspect_missing_overall_counts,
                "missing_aspects_scraped_counts": aspect_missing_scraped_counts,
            },
        },
        "chassis_reviews": dedup_chassis_list,
    }


def format_youtube_gap_tasks_md(output_payload: Dict[str, Any]) -> str:
    """Format the 3-person YouTube gap fill markdown report from an audited Format B2 payload."""
    meta = output_payload.get("audit_metadata") or {}
    summary = meta.get("deduplication_summary") or {}
    dedup_chassis_list = output_payload.get("chassis_reviews") or []
    unmatched_cids = list(meta.get("unmatched_canonical_ids") or [])
    cat_laptop_count = int(meta.get("catalog_laptops_count") or 0)

    aspect_missing_scraped = summary.get("missing_aspects_scraped_counts") or {a: 0 for a in CRITICAL_ASPECTS}
    aspect_missing_overall = summary.get("missing_aspects_overall_counts") or {a: 0 for a in CRITICAL_ASPECTS}

    incomplete = [c for c in dedup_chassis_list if c["audit_metrics"]["priority"] != "OK"]
    incomplete.sort(
        key=lambda c: (
            -c["sku_count_in_catalog"],
            c["audit_metrics"]["scraped_doc_count"],
            -len(c["audit_metrics"]["missing_aspects_scraped"]),
            c["chassis_key"],
        )
    )

    names = ["Person 1", "Person 2", "Person 3"]
    team: Dict[str, List[Dict[str, Any]]] = {name: [] for name in names}
    for idx, ch in enumerate(incomplete):
        team[names[idx % 3]].append(ch)

    lines: List[str] = [
        "# 3-Person YouTube Review Search & Gap Fill Plan",
        "",
        "## 1. Deduplication & Catalogue Audit Summary",
        "",
        f"- **Catalogue SKUs Checked:** `{cat_laptop_count}` (`{len(unmatched_cids)}` SKU missing from reviews JSON: `{', '.join(unmatched_cids) if unmatched_cids else 'None'}`)",
        f"- **Review Entries Audited:** `{summary.get('raw_target_entries', 0)}` raw targets merged into **`{summary.get('unique_chassis_count', 0)}` unique chassis entries**.",
        f"- **Chunks Processed:** `{summary.get('input_chunks_considered', 0)}` input chunks -> **`{summary.get('exact_duplicates_removed', 0)}` exact duplicates** and **`{summary.get('near_duplicates_removed', 0)}` near-duplicates (cosine > 0.90)** removed (`{summary.get('synthesized_yt_fallbacks_stripped', 0)}` synthetic YouTube fallback duplicates stripped); **`{summary.get('kept_chunks_total', 0)}` unique chunks kept** (`{summary.get('explicit_pro_con_chunks', 0)}` explicitly labeled pro/con, `{summary.get('inferred_pro_con_chunks', 0)}` sentiment-verified from discussions/verdicts).",
        f"- **Real Scraped Review Coverage:** `{summary.get('zero_scraped_doc_chassis', 0)}` chassis have **`0` docs**, `{summary.get('one_scraped_doc_chassis', 0)}` chassis have **`1` doc** (**`{summary.get('high_priority_chassis_0_or_1_doc', 0)}` High Priority total**), `{summary.get('medium_priority_chassis', 0)}` chassis are **Medium Priority** (missing real scraped balance/aspects), and `{summary.get('complete_chassis', 0)}` chassis have full scraped + synthesized coverage.",
        f"- **Missing Critical Aspects (Real Scraped Reviews):** Thermals: `{aspect_missing_scraped.get('thermals', 0)}`, Battery: `{aspect_missing_scraped.get('battery', 0)}`, Screen: `{aspect_missing_scraped.get('screen', 0)}`, Build/Hinges: `{aspect_missing_scraped.get('build_quality', 0)}`.",
        f"- **Missing Critical Aspects (Even Including Synthesized Text):** Thermals: `{aspect_missing_overall.get('thermals', 0)}`, Battery: `{aspect_missing_overall.get('battery', 0)}`, Screen: `{aspect_missing_overall.get('screen', 0)}`, Build/Hinges: `{aspect_missing_overall.get('build_quality', 0)}`.",
        f"- **Total Incomplete Chassis Ranked for YouTube Fill:** **`{len(incomplete)}`** (covering `{sum(c['sku_count_in_catalog'] for c in incomplete)}` catalog SKUs), split evenly into 3 lists below (most common catalog chassis first).",
        "",
    ]

    for person in names:
        plist = team[person]
        sku_cov = sum(c["sku_count_in_catalog"] for c in plist)
        hp_cnt = sum(1 for c in plist if c["audit_metrics"]["priority"] == "High Priority")
        lines.append("---")
        lines.append("")
        lines.append(f"## {person} ({len(plist)} Chassis | {sku_cov} Catalog SKUs | {hp_cnt} High Priority)")
        lines.append("")
        lines.append("| # | Priority | SKUs | Docs | Laptop Model (`chassis_key`) | Missing | Suggested YouTube Search Queries (EN & AR) |")
        lines.append("| :---: | :---: | :---: | :---: | :--- | :--- | :--- |")

        for rank, ch in enumerate(plist, start=1):
            m = ch["audit_metrics"]
            ident = ch["identity"]
            brand = str(ident.get("brand") or "").strip()
            fam = str(ident.get("laptop_family") or "").strip()
            model = str(ident.get("laptop_model") or ch["chassis_key"]).replace("|", "/")
            short_model = re.sub(r"\s*\(Machine Type:[^)]+\)", "", model).split(" - ")[0].split(" – ")[0].strip()
            if fam and fam.lower() not in short_model.lower() and fam.lower() not in ("hp", "hp essential", "lenovo", "ultra 7"):
                short_model = f"{fam} {short_model}".strip()
            if brand and brand.lower() not in short_model.lower():
                short_model = f"{brand} {short_model}".strip()
            short_model = short_model[:72].strip()

            missing_parts: List[str] = []
            if m["scraped_doc_count"] == 0:
                missing_parts.append("0 Scraped Docs")
            elif m["scraped_doc_count"] == 1:
                missing_parts.append("Only 1 Doc")
            for bg in m["balance_gaps"]:
                if bg not in missing_parts:
                    missing_parts.append(bg)
            for asp in CRITICAL_ASPECTS:
                if asp in m["missing_aspects_overall"]:
                    missing_parts.append(f"{ASPECT_LABELS_EN[asp]} (All)")
                elif asp in m["missing_aspects_scraped"]:
                    missing_parts.append(ASPECT_LABELS_EN[asp])

            missing_str = "Missing: " + (", ".join(missing_parts) if missing_parts else "Review depth")
            focus_en = " ".join(ASPECT_LABELS_EN[a].lower() for a in (m["missing_aspects_scraped"] or CRITICAL_ASPECTS)[:3])
            focus_ar = " ".join(ASPECT_LABELS_AR[a] for a in (m["missing_aspects_scraped"] or CRITICAL_ASPECTS)[:3])
            if m["balance_gaps"]:
                focus_en += " pros cons"
                focus_ar += " عيوب ومميزات"

            q_en = f"`{short_model} review {focus_en}`"
            q_ar = f"`مراجعة لابتوب {short_model} {focus_ar}`"

            lines.append(
                f"| {rank} | {m['priority']} | {ch['sku_count_in_catalog']} | {m['scraped_doc_count']} | "
                f"**{short_model}**<br>`{ch['chassis_key']}` | {missing_str} | **EN:** {q_en}<br>**AR:** {q_ar} |"
            )
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "ASPECT_KEYWORDS",
    "CON_SIGNAL_KEYWORDS",
    "CRITICAL_ASPECTS",
    "PRO_SIGNAL_KEYWORDS",
    "audit_and_deduplicate_payload",
    "char_word_features",
    "cosine_sim_sparse",
    "dedup_chunks_cosine",
    "format_youtube_gap_tasks_md",
    "infer_review_polarity",
    "normalize_review_text",
    "select_transcript_chunks",
    "split_review_sentences",
    "tag_review_aspects",
]
