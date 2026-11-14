#!/usr/bin/env python3
"""
Raw Reviews Enricher (Format A -> Enriched Format B1)
====================================================
Converts Raw Scraper Format A (`laptops[]` with `youtube` and `communities`) into
Enriched Format B1 (`nlp_review_profile` with calibrated aspect scores, `pros_en`,
`pros_ar`, `cons_en`, `cons_ar`, `synthesized_review_en`, `synthesized_review_ar`).

Pipeline per chassis:
1. Local `Jina-v3` noise filtering + transcript chunking + top hardware-relevant
   sentence extraction & 10-anchor semantic scoring.
2. Primary -> Fallback LLM synthesis over SovereignEG OpenAI-compatible HTTP API
   (`ENRICHER_LLM_BASE_URL`, `ENRICHER_LLM_API_KEY`, `ENRICHER_PRIMARY_MODEL` ->
   automatic retry on `ENRICHER_FALLBACK_MODEL` if JSON schema or Arabic check fails).
3. Automatic `zero_llm` (`Jina-v3` anchor scoring + grounded spec/evidence templates)
   as offline fallback when API credentials/network are unavailable or all LLMs fail.
4. SHA-256 delta hash cache (`enricher_delta_cache.json`) so only new/changed
   chassis hit the remote LLM endpoint.
5. Physical hardware anchoring via `chroma_reviews_engine._recalibrate_item` while
   keeping raw baseline aspect ratings in `synthesized_review_en` for idempotency.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import httpx
import numpy as np
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Environment & Shared Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DELTA_CACHE_PATH = "enricher_delta_cache.json"
ENRICHER_SCHEMA_VERSION = "v2_yt_pipeline"
DEFAULT_PRIMARY_MODEL = "claude-haiku-5.5"
DEFAULT_FALLBACK_MODEL = "gpt-oss-120b"

ASPECT_KEYS: Tuple[str, ...] = (
    "thermals_score",
    "acoustics_score",
    "build_and_hinges_score",
    "keyboard_and_trackpad_score",
    "real_battery_and_reliability_score",
)

# Verified against SovereignEG GET /v1/models EGP pricing
SOVEREIGNEG_PRICING_EGP_PER_1M: Dict[str, Dict[str, float]] = {
    "qwen3.7-flash": {"input": 1.7656, "output": 7.6508},
    "gpt-oss-120b": {"input": 2.1775, "output": 10.0049},
    "claude-haiku-5.5": {"input": 5.8852, "output": 29.4261},
}

ENRICHMENT_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["aspect_scores", "pros_en", "pros_ar", "cons_en", "cons_ar"],
    "properties": {
        "aspect_scores": {
            "type": "object",
            "additionalProperties": False,
            "required": list(ASPECT_KEYS),
            "properties": {k: {"type": "number"} for k in ASPECT_KEYS},
        },
        "pros_en": {
            "type": "array",
            "items": {"type": "string"},
        },
        "pros_ar": {
            "type": "array",
            "items": {"type": "string"},
        },
        "cons_en": {
            "type": "array",
            "items": {"type": "string"},
        },
        "cons_ar": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}

_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")
_CODE_BLOCK_RE = re.compile(r"```.*?```", flags=re.DOTALL)
_DETAILS_BLOCK_RE = re.compile(r"<details>.*?</details>", flags=re.DOTALL | re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)

_NOISE_PATTERNS = re.compile(
    r"(?i)(subscribe to (my|the) channel|hit the bell|like and subscribe|"
    r"check out (the )?links? (in the )?description|use my (affiliate )?code|"
    r"sponsored by|this video is sponsored|patreon\.com|gaminglaptop\.deals|"
    r"should i buy this|which laptop should i get|can anyone help|"
    r"pls help|please help|bazzite|lspci|lsmod|modinfo|kernel modules|"
    r"بكام|سعره كام|ممكن ترشيح|تنصحوني بإيه|حد جرب الجهاز|ازاي اثبت ويندوز)"
)

_DESKTOP_PART_RE = re.compile(
    r"(?i)(?:\b(?:B850M?|B860M?|B760M?|B650M?|X870E?|Z790|Z890|H610|A620|AM5|LGA\s?1[78]51|"
    r"mini-?ATX|micro-?ATX|motherboard|DisplayPort\s*2\.1b?|3\.\d+-?slot|GDDR7.*192bit)\b|"
    r"(?:ال)?لوحة\s+(?:ال)?أم|كارت\s+الشاشة|تجميعة|فتحة\s+PCIe)"
)
_LAPTOP_CONTEXT_RE = re.compile(
    r"(?i)(?:\b(?:laptop|notebook|battery|whr|hinge|hinges|trackpad|touchpad|"
    r"webcam|charger|adapter|lid|keyboard flex|portability)\b|لابتوب|بطارية|مفصلات|تاتش باد)"
)

# 10 Semantic Anchors (Pro + Con per aspect) + 1 Noise anchor for Jina-v3 filtering
_PRO_ANCHORS: Dict[str, str] = {
    "thermals_score": (
        "Effective cooling performance, low CPU and GPU temperatures under gaming or stress loads, "
        "vapor chamber or heatpipes, cool keyboard surface, no thermal throttling. "
        "نظام تبريد ممتاز وحرارة منخفضة تحت الضغط بدون اختناق حراري"
    ),
    "acoustics_score": (
        "Quiet fan operation during everyday work and reasonable low fan noise under gaming load, "
        "no high-pitched coil whine. مراوح هادئة وصوت منخفض بدون ضوضاء مزعجة"
    ),
    "build_and_hinges_score": (
        "Solid aluminum or rigid chassis construction, zero deck flex, smooth sturdy hinges, "
        "premium durable build quality and good upgradeability. "
        "شاسيه متين وألومنيوم قوي ومفصلات ثابتة وجودة تصنيع عالية"
    ),
    "keyboard_and_trackpad_score": (
        "Comfortable tactile keyboard with good key travel, clean backlight, and large smooth "
        "responsive glass touchpad. كيبورد مريح للكتابة وتاتش باد سلس ودقيق"
    ),
    "real_battery_and_reliability_score": (
        "Long real-world battery life lasting many hours unplugged, bright 100% sRGB or OLED display, "
        "good color accuracy, dependable everyday reliability. "
        "بطارية تدوم طويلاً وشاشة مشرقة بألوان دقيقة واعتمادية ممتازة"
    ),
}

_CON_ANCHORS: Dict[str, str] = {
    "thermals_score": (
        "High CPU or GPU overheating up to 95-100 degrees Celsius, thermal throttling, "
        "hot keyboard or palm rest during load. سخونة عالية وارتفاع حرارة المعالج واختناق حراري"
    ),
    "acoustics_score": (
        "Very loud roaring turbo fan noise under load, jet-engine fans requiring headphones, "
        "annoying coil whine. صوت مراوح عالي جداً ومزعج مع الألعاب والضغط"
    ),
    "build_and_hinges_score": (
        "Cheap plastic build, noticeable keyboard deck or lid flex, wobbly weak hinges, "
        "fingerprint magnet or creaking frame. خامات بلاستيكية ضعيفة ومفصلات مهتزة"
    ),
    "keyboard_and_trackpad_score": (
        "Shallow mushy keyboard keys, cramped arrow or numpad layout, rattling or stiff small "
        "plastic trackpad. كيبورد ضعيف أو تاتش باد صغير غير مريح"
    ),
    "real_battery_and_reliability_score": (
        "Short poor battery life under 3-4 hours, dim washed-out 45% NTSC 250-nit screen, "
        "backlight bleed, driver crashes or hardware defects. "
        "بطارية ضعيفة تفرغ بسرعة أو شاشة باهتة وسطوع منخفض أو مشاكل اعتمادية"
    ),
}

_NOISE_ANCHOR = (
    "YouTube channel subscription reminder, affiliate link promotion, sponsor ad read, "
    "unrelated desktop motherboard specs, Linux kernel driver log, or user buying question. "
    "إعلان قناة أو سؤال شراء من مستخدم أو مواصفات قطع كمبيوتر مكتبي"
)

_ASPECT_KEYWORDS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "thermals_score": {
        "pro": ("cool", "cooling", "thermal", "temp", "degrees", "heatsink", "heatpipe", "vapor chamber", "no throttling", "تبريد", "حرارة ممتازة"),
        "con": ("overheat", "throttl", "throttle", "95c", "95°c", "99c", "100c", "runs hot", "very hot", "سخونة", "حرارة عالية", "اختناق"),
    },
    "acoustics_score": {
        "pro": ("quiet", "silent", "inaudible", "low fan noise", "هادئ", "صوت هادئ"),
        "con": ("loud", "noisy", "jet engine", "annoying fan", "coil whine", "whine", "decibel", "db", "مزعج", "صوت المراوح عالي"),
    },
    "build_and_hinges_score": {
        "pro": ("aluminum", "metal", "magnesium", "sturdy", "solid", "rigid", "mil-std", "hinge", "upgrad", "ram slot", "m.2", "معدن", "متين", "مفصلات قوية"),
        "con": ("plastic", "flex", "wobble", "cheap", "flimsy", "creak", "fingerprint", "soldered ram", "بلاستيك", "اهتزاز", "مفصلات ضعيفة"),
    },
    "keyboard_and_trackpad_score": {
        "pro": ("tactile", "key travel", "comfortable keyboard", "backlit", "rgb", "glass touchpad", "smooth trackpad", "كيبورد مريح", "تاتش باد"),
        "con": ("mushy", "shallow", "cramped", "rattle", "rattly", "small touchpad", "stiff trackpad", "كيبورد ضعيف", "تاتش باد صغير"),
    },
    "real_battery_and_reliability_score": {
        "pro": ("battery life", "hours", "90wh", "90-w", "80wh", "70wh", "oled", "100% srgb", "bright", "nits", "accurate colors", "mux", "بطارية ممتازة", "شاشة ممتازة"),
        "con": ("poor battery", "short battery", "45% ntsc", "dim", "250 nits", "washed out", "bleed", "backlight bleed", "latency", "glitch", "بطارية ضعيفة", "شاشة باهتة"),
    },
}

_ASPECT_FALLBACK_AR: Dict[str, Tuple[str, str]] = {
    "thermals_score": (
        "أداء تبريد مستقر نسبياً يحافظ على ترددات المعالج وكارت الشاشة في المهام اليومية والألعاب المتوسطة",
        "قد ترتفع درجات حرارة المعالج تحت الضغط المتواصل مما يتطلب تهوية جيدة أو قاعدة تبريد في الصيف",
    ),
    "acoustics_score": (
        "صوت المراوح مقبول وهادئ في أوضاع الاستخدام العادي والتصفح",
        "صوت المراوح يرتفع بوضوح عند تشغيل وضع الأداء الأقصى أو الألعاب الثقيلة",
    ),
    "build_and_hinges_score": (
        "جودة تصنيع جيدة وتصميم عملي يتحمل التنقل والعمل اليومي مع مفصلات ثابتة",
        "وجود بعض المرونة أو الاعتماد على خامات بلاستيكية في أجزاء من الهيكل الخارجي مقارنة بالفئات المعدنية",
    ),
    "keyboard_and_trackpad_score": (
        "كيبورد مريح للاستخدام والكتابة الطويلة مع لوحة لمس دقيقة وسلسة الاستجابة",
        "تخطيط بعض الأزرار أو حجم لوحة اللمس قد لا يناسب جميع المستخدمين مقارنة بالأجهزة الأعلى فئة",
    ),
    "real_battery_and_reliability_score": (
        "توازن جيد بين الشاشة والبطارية يناسب مهام الدراسة والعمل المتنقل بثبات",
        "عمر البطارية أو سطوع الشاشة وتغطية الألوان يظل متوسطاً ولا يناسب العمل الطويل بدون شاحن في المهام الشاقة",
    ),
}

_ASPECT_FALLBACK_EN: Dict[str, Tuple[str, str]] = {
    "thermals_score": (
        "Thermals remain controlled under sustained workloads without severe CPU/GPU throttling",
        "CPU/GPU temperatures climb noticeably under heavy stress tests in warm ambient conditions",
    ),
    "acoustics_score": (
        "Fans stay unobtrusive during light productivity and quiet-mode operation",
        "Fan noise ramps up noticeably during Turbo or sustained gaming loads",
    ),
    "build_and_hinges_score": (
        "Sturdy everyday chassis construction with dependable hinges and solid upgradeability",
        "Plastic chassis panels exhibit minor flex compared to all-aluminum premium ultrabooks",
    ),
    "keyboard_and_trackpad_score": (
        "Comfortable keyboard travel and responsive touchpad suited for daily typing",
        "Keyboard key travel or touchpad feel is average for the price tier",
    ),
    "real_battery_and_reliability_score": (
        "Display clarity and battery efficiency deliver solid day-to-day reliability",
        "Unplugged battery endurance and outdoor display brightness/color gamut remain modest",
    ),
}

_EMBED_FN_SINGLETON: Any = None
_ANCHOR_EMBS_CACHE: Optional[Dict[str, Any]] = None


def load_enricher_env() -> None:
    """Load `.env` from script directory and current working directory without overriding env vars."""
    candidates = [SCRIPT_DIR / ".env", Path.cwd() / ".env"]
    seen = set()
    for p in candidates:
        rp = str(p.resolve()) if p.exists() else str(p)
        if rp in seen:
            continue
        seen.add(rp)
        if p.exists():
            load_dotenv(p, override=False)


load_enricher_env()


def _get_jina_embed_fn():
    """Return a singleton JinaV3EmbeddingFunction (retrieval.passage, dim=512)."""
    global _EMBED_FN_SINGLETON
    if _EMBED_FN_SINGLETON is None:
        from chroma_reviews_engine import EMBED_DIM, MODEL_NAME, JinaV3EmbeddingFunction

        _EMBED_FN_SINGLETON = JinaV3EmbeddingFunction(
            model_name=MODEL_NAME,
            task="retrieval.passage",
            truncate_dim=EMBED_DIM,
        )
    return _EMBED_FN_SINGLETON


def _get_anchor_embeddings() -> Dict[str, Any]:
    """Compute and cache normalized embeddings for the 10 aspect anchors + 1 noise anchor."""
    global _ANCHOR_EMBS_CACHE
    if _ANCHOR_EMBS_CACHE is not None:
        return _ANCHOR_EMBS_CACHE

    emb_fn = _get_jina_embed_fn()
    keys_and_texts: List[Tuple[str, str, str]] = []
    for k in ASPECT_KEYS:
        keys_and_texts.append(("pro", k, _PRO_ANCHORS[k]))
        keys_and_texts.append(("con", k, _CON_ANCHORS[k]))
    keys_and_texts.append(("noise", "noise", _NOISE_ANCHOR))

    vecs = np.asarray(emb_fn([t for _, _, t in keys_and_texts]), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms

    pro_vecs = np.stack([vecs[i] for i, (kind, _, _) in enumerate(keys_and_texts) if kind == "pro"])
    con_vecs = np.stack([vecs[i] for i, (kind, _, _) in enumerate(keys_and_texts) if kind == "con"])
    noise_vec = vecs[-1]

    _ANCHOR_EMBS_CACHE = {
        "pro": pro_vecs,
        "con": con_vecs,
        "noise": noise_vec,
    }
    return _ANCHOR_EMBS_CACHE


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


def detect_reviews_format(payload: Any) -> str:
    """
    Auto-detect review dataset schema:
    - 'format_b2_deduplicated': `chassis_reviews[]` payload from `audit_and_deduplicate_reviews.py`
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


# ---------------------------------------------------------------------------
# Noise Filtering & Local Jina-v3 Evidence Extraction
# ---------------------------------------------------------------------------

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


def _gather_raw_candidate_chunks(item: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
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

    specs = (cat_entry or {}).get("specs", {})
    dm = (cat_entry or {}).get("derived_metrics", {})
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


_HW_UNIT_RE = re.compile(
    r"(?i)\b(\d+\s*(?:w|wh|whr|hz|nits|db|°c|fps|gb|tb|mm|hrs?|hours?|ms|%)|"
    r"cpu|gpu|rtx|gtx|ryzen|core\s+ultra|oled|ips|srgb|ntsc|battery|charging|"
    r"thermal|cool|heat|throttl|fan|loud|quiet|noise|hinge|build|plastic|"
    r"aluminum|metal|flex|keyboard|trackpad|touchpad|display|screen|bright|"
    r"speaker|port|upgrad\w*|ram|ssd|wifi)\b|"
    r"حرارة|تبريد|مراوح|صوت|بطارية|شاشة|مفصلات|خامات|كيبورد|تاتش"
)


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


def _score_and_select_evidence_for_item(
    chassis_key: str,
    unique_cands: List[Dict[str, Any]],
    doc_count: int,
    specs_summary: Dict[str, Any],
    vecs: np.ndarray,
    anchors: Dict[str, Any],
    max_snippets: int = 20,
    dedup_cosine: float = 0.88,
) -> Dict[str, Any]:
    """Run 10-anchor Jina cosine scoring, noise rejection, and cosine dedup for one chassis."""
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


def extract_hardware_sentences_jina(
    item: Dict[str, Any],
    cat_map: Optional[Dict[str, Any]] = None,
    max_snippets: int = 16,
    dedup_cosine: float = 0.88,
    max_candidates: int = 24,
) -> Dict[str, Any]:
    """
    Use local `Jina-v3` (512-dim) embeddings to filter out noisy/off-topic lines,
    deduplicate near-identical chunks, select the top `max_snippets` hardware-relevant
    sentences across aspects & sources, and compute Jina 10-anchor aspect signals.
    """
    return extract_hardware_sentences_jina_batch(
        items=[item],
        cat_map=cat_map,
        max_snippets=max_snippets,
        dedup_cosine=dedup_cosine,
        max_candidates=max_candidates,
    )[0]


def extract_hardware_sentences_jina_batch(
    items: List[Dict[str, Any]],
    cat_map: Optional[Dict[str, Any]] = None,
    max_snippets: int = 16,
    dedup_cosine: float = 0.88,
    max_candidates: int = 24,
    encode_slice_size: int = 256,
) -> List[Dict[str, Any]]:
    """
    Batch-extract Jina-v3 hardware evidence across multiple chassis with global
    length sorting to minimize Transformer padding overhead on CPU.
    """
    prepared: List[Tuple[str, List[Dict[str, Any]], int, Dict[str, Any]]] = []
    flat_texts: List[Tuple[int, int, str]] = []

    for item_idx, item in enumerate(items):
        ckey = str(item.get("chassis_key") or "")
        candidates, doc_count = _gather_raw_candidate_chunks(item)
        specs_summary = _format_catalog_specs_summary(item, cat_map)
        unique_cands = _select_top_candidates_for_jina(candidates, max_candidates=max_candidates)
        prepared.append((ckey, unique_cands, doc_count, specs_summary))
        for cand_idx, c in enumerate(unique_cands):
            flat_texts.append((item_idx, cand_idx, c["text"]))

    if not flat_texts:
        return [
            _score_and_select_evidence_for_item(
                chassis_key=ckey,
                unique_cands=[],
                doc_count=doc_count,
                specs_summary=specs_summary,
                vecs=np.empty((0, 512), dtype=np.float32),
                anchors={"pro": np.empty((0, 512)), "con": np.empty((0, 512)), "noise": np.empty((512,))},
                max_snippets=max_snippets,
                dedup_cosine=dedup_cosine,
            )
            for ckey, _, doc_count, specs_summary in prepared
        ]

    emb_fn = _get_jina_embed_fn()
    anchors = _get_anchor_embeddings()

    # Global length sort minimizes attention padding per batch on CPU
    sorted_refs = sorted(flat_texts, key=lambda x: len(x[2]))
    total_texts = len(sorted_refs)
    sorted_vecs: List[np.ndarray] = []

    model_obj = getattr(emb_fn, "_model", None)
    prev_max_seq = getattr(model_obj, "max_seq_length", 256) if model_obj is not None else None
    try:
        if model_obj is not None:
            model_obj.max_seq_length = 96
        for start in range(0, total_texts, encode_slice_size):
            batch_strs = [row[2] for row in sorted_refs[start : start + encode_slice_size]]
            bvecs = np.asarray(emb_fn(batch_strs), dtype=np.float32)
            norms = np.linalg.norm(bvecs, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            bvecs = bvecs / norms
            sorted_vecs.append(bvecs)
            if total_texts > encode_slice_size:
                done_n = min(start + encode_slice_size, total_texts)
                print(f"  [Jina-v3 batch] Encoded {done_n}/{total_texts} candidate chunks...")
    finally:
        if model_obj is not None:
            model_obj.max_seq_length = prev_max_seq if prev_max_seq is not None else 256

    all_vecs = np.concatenate(sorted_vecs, axis=0)
    per_item_slots: List[List[Optional[np.ndarray]]] = [
        [None] * len(prep[1]) for prep in prepared
    ]
    for pos, (item_idx, cand_idx, _) in enumerate(sorted_refs):
        per_item_slots[item_idx][cand_idx] = all_vecs[pos]

    outputs: List[Dict[str, Any]] = []
    for item_idx, (ckey, unique_cands, doc_count, specs_summary) in enumerate(prepared):
        if unique_cands:
            item_vecs = np.stack([v for v in per_item_slots[item_idx] if v is not None])
        else:
            item_vecs = np.empty((0, 512), dtype=np.float32)
        outputs.append(
            _score_and_select_evidence_for_item(
                chassis_key=ckey,
                unique_cands=unique_cands,
                doc_count=doc_count,
                specs_summary=specs_summary,
                vecs=item_vecs,
                anchors=anchors,
                max_snippets=max_snippets,
                dedup_cosine=dedup_cosine,
            )
        )
    return outputs


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


# ---------------------------------------------------------------------------
# Physical Recalibration & Synthesized Summary Builders
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
    Finalize a Format B1 `nlp_review_profile` using `chroma_reviews_engine._recalibrate_item`
    while preserving raw baseline aspect scores in `synthesized_review_en`.
    """
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
        from chroma_reviews_engine import _recalibrate_item

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


# ---------------------------------------------------------------------------
# Mode A: Zero-LLM Grounded Enrichment (Offline Fallback)
# ---------------------------------------------------------------------------

def enrich_chassis_zero_llm(
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
        evidence_pack = extract_hardware_sentences_jina(item, cat_map=cat_map)

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


# ---------------------------------------------------------------------------
# Mode B: SovereignEG LLM Client + Primary -> Fallback -> zero_llm Chain
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


def _call_sovereigneg_model(
    model: str,
    messages: List[Dict[str, str]],
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_sec: float = 90.0,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Call SovereignEG OpenAI-compatible `/chat/completions` for `model`.
    Handles model-specific capabilities (`supports_temperature: False` on `claude*`,
    `json_schema` structured outputs with fallback to prompt-only JSON if HTTP 400,
    and `reasoning_effort='low'` on `gpt-oss*`).
    Returns `(parsed_json_or_None, call_telemetry)`.
    """
    load_enricher_env()
    url_base = (base_url or os.getenv("ENRICHER_LLM_BASE_URL") or "").strip().rstrip("/")
    token = (api_key or os.getenv("ENRICHER_LLM_API_KEY") or "").strip()
    if not url_base or not token:
        return None, {
            "model": model,
            "latency_sec": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_egp": 0.0,
            "http_status": None,
            "error": "Missing ENRICHER_LLM_BASE_URL or ENRICHER_LLM_API_KEY",
        }

    endpoint = f"{url_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    m_low = model.lower()
    req_messages = [
        (
            {"role": m["role"], "content": str(m.get("content") or "") + "\n/no_think"}
            if "qwen" in m_low and m.get("role") == "system"
            else dict(m)
        )
        for m in messages
    ]

    if "qwen" in m_low:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": req_messages,
            "max_tokens": 4096,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }
    else:
        payload = {
            "model": model,
            "messages": req_messages,
            "max_tokens": 3000,
            "reasoning_effort": "low",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "laptop_review_enrichment",
                    "strict": True,
                    "schema": ENRICHMENT_JSON_SCHEMA,
                },
            },
        }
        if "claude" not in m_low:
            payload["temperature"] = 0.2

    t0 = time.perf_counter()
    http_status: Optional[int] = None
    last_err = ""
    resp_json: Dict[str, Any] = {}

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(endpoint, headers=headers, json=payload)
            http_status = resp.status_code
            # Retry selectively on HTTP 400 if provider rejects optional thinking or format params
            if resp.status_code == 400:
                err_body = resp.text.lower()
                retry_payload = dict(payload)
                changed = False
                if "chat_template_kwargs" in retry_payload and (
                    "chat_template_kwargs" in err_body
                    or "enable_thinking" in err_body
                    or "extra" in err_body
                    or "unknown" in err_body
                    or "unrecognized" in err_body
                ):
                    retry_payload.pop("chat_template_kwargs", None)
                    changed = True
                if "reasoning_effort" in err_body and "reasoning_effort" in retry_payload:
                    retry_payload.pop("reasoning_effort", None)
                    changed = True
                if "response_format" in err_body and "response_format" in retry_payload:
                    retry_payload.pop("response_format", None)
                    changed = True
                if not changed and "chat_template_kwargs" in retry_payload:
                    retry_payload.pop("chat_template_kwargs", None)
                    changed = True
                if changed:
                    resp = client.post(endpoint, headers=headers, json=retry_payload)
                    http_status = resp.status_code
            resp.raise_for_status()
            resp_json = resp.json()
    except Exception as exc:
        last_err = f"{type(exc).__name__}: {str(exc)[:240]}"
        return None, {
            "model": model,
            "latency_sec": round(time.perf_counter() - t0, 4),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_egp": 0.0,
            "http_status": http_status,
            "error": last_err,
        }

    elapsed = round(time.perf_counter() - t0, 4)
    usage = resp_json.get("usage") or {}
    ptok = int(usage.get("prompt_tokens") or 0)
    ctok = int(usage.get("completion_tokens") or 0)
    rtok = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    ttok = int(usage.get("total_tokens") or (ptok + ctok))
    cost_egp = _estimate_egp_cost(model, ptok, ctok)

    choices = resp_json.get("choices") or []
    raw_content = ""
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        raw_content = str(msg.get("content") or "").strip()

    try:
        parsed = _extract_json_from_llm_content(raw_content)
    except Exception as exc:
        return None, {
            "model": model,
            "latency_sec": elapsed,
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
            "reasoning_tokens": rtok,
            "total_tokens": ttok,
            "estimated_cost_egp": cost_egp,
            "http_status": http_status,
            "error": f"JSON parse failed: {type(exc).__name__}: {exc}",
        }

    return parsed, {
        "model": model,
        "latency_sec": elapsed,
        "prompt_tokens": ptok,
        "completion_tokens": ctok,
        "reasoning_tokens": rtok,
        "total_tokens": ttok,
        "estimated_cost_egp": cost_egp,
        "http_status": http_status,
        "error": None,
    }


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
    llm_caller: Optional[Callable[..., Tuple[Optional[Dict[str, Any]], Dict[str, Any]]]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Enrich one chassis using:
      - mode='zero_llm': local Jina-v3 anchor scoring only.
      - mode='single_model': call `primary_model` only (still falls back to `zero_llm` if fail).
      - mode='primary_with_fallback': call `primary_model` -> if schema/Arabic check fails,
        retry on `fallback_model` -> if still invalid/offline, fall back to `zero_llm`.
    """
    if evidence_pack is None:
        evidence_pack = extract_hardware_sentences_jina(item, cat_map=cat_map)

    if mode == "zero_llm":
        return enrich_chassis_zero_llm(
            item=item,
            cat_map=cat_map,
            evidence_pack=evidence_pack,
            preserve_existing_bullets=preserve_existing_bullets,
        )

    load_enricher_env()
    p_model = (primary_model or os.getenv("ENRICHER_PRIMARY_MODEL") or DEFAULT_PRIMARY_MODEL).strip()
    f_model = (fallback_model or os.getenv("ENRICHER_FALLBACK_MODEL") or DEFAULT_FALLBACK_MODEL).strip()
    caller = llm_caller or _call_sovereigneg_model
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
    prof, z_tel = enrich_chassis_zero_llm(
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


# ---------------------------------------------------------------------------
# Delta Hash Cache & Dataset-Wide Batch Enricher
# ---------------------------------------------------------------------------

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
            comm_items.append(
                {
                    "bucket": bname,
                    "post_id": str(p.get("post_id") or p.get("post_url") or ""),
                    "title": str(p.get("post_title") or p.get("title") or ""),
                    "body_hash": hashlib.sha256(
                        str(p.get("post_body") or p.get("body") or p.get("text") or "").encode("utf-8")
                    ).hexdigest(),
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


def _load_json_dict(path: Optional[Union[str, Path]]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json_atomic(path: Union[str, Path], data: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def enrich_reviews_dataset(
    payload_or_path: Union[str, Path, Dict[str, Any]],
    catalog_path: str = "unified_catalog_topsis_ready_v6.json",
    delta_cache_path: Optional[str] = DEFAULT_DELTA_CACHE_PATH,
    primary_model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    mode: str = "primary_with_fallback",
    force: bool = False,
    only_missing_or_delta: bool = True,
    max_workers: int = 8,
    preserve_existing_bullets: bool = False,
    output_path: Optional[str] = None,
    llm_caller: Optional[Callable[..., Tuple[Optional[Dict[str, Any]], Dict[str, Any]]]] = None,
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
        with open(catalog_path, "r", encoding="utf-8") as f:
            cat_raw = json.load(f)
        cat_map = {l["canonical_id"]: l for l in cat_raw.get("laptops", []) if "canonical_id" in l}

    load_enricher_env()
    eff_primary = (primary_model or os.getenv("ENRICHER_PRIMARY_MODEL") or DEFAULT_PRIMARY_MODEL).strip()

    delta_cache = _load_json_dict(delta_cache_path)
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
        batch_packs = extract_hardware_sentences_jina_batch(
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
        prof, tel = enrich_chassis_with_fallback(
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
        if mode == "zero_llm" or ptaken in ("primary", "fallback"):
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
                        _save_json_atomic(delta_cache_path, delta_cache)
                    if output_path:
                        _save_json_atomic(output_path, data)

    if isinstance(data.get("batch_metadata"), dict):
        data["batch_metadata"]["last_enrichment_mode"] = mode
        data["batch_metadata"]["total_chassis"] = len(laptops)

    if delta_cache_path and completed_count:
        delta_cache["schema_version"] = ENRICHER_SCHEMA_VERSION
        _save_json_atomic(delta_cache_path, delta_cache)

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


if __name__ == "__main__":
    import argparse

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
