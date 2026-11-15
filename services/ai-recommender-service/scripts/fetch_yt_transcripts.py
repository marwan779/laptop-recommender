"""Fault-tolerant YouTube transcript batch fetcher for team-split execution.

Supports both youtube-transcript-api v0.6.x (class methods) and v1.x (instance
methods), prefers Arabic ('ar') then English ('en', 'en-US', 'en-GB'), caches
already-fetched video IDs across resumes and duplicate batch entries, writes
progress atomically after every video, and sleeps randomly between requests.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

PREFERRED_LANGUAGES = ("ar", "en", "en-US", "en-GB")
RATE_LIMIT_KEYWORDS = (
    "429",
    "too many requests",
    "ipblocked",
    "requestblocked",
    "blocked",
    "captcha",
)


def _import_yt_api():
    """Import youtube_transcript_api lazily so --help works before installing it."""
    try:
        import youtube_transcript_api as yt_mod
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'youtube-transcript-api'. "
            "Install it with: pip install youtube-transcript-api"
        ) from exc

    api_cls = yt_mod.YouTubeTranscriptApi
    no_transcript = getattr(yt_mod, "NoTranscriptFound", Exception)
    disabled = getattr(yt_mod, "TranscriptsDisabled", Exception)
    unavailable = getattr(yt_mod, "VideoUnavailable", Exception)
    return api_cls, no_transcript, disabled, unavailable


def _extract_segments_text(fetched: Any) -> str:
    """Join transcript snippet objects or dicts into a clean single-spaced string."""
    parts: list[str] = []
    for seg in fetched:
        text = seg.text if hasattr(seg, "text") else seg.get("text", "")
        cleaned = " ".join(str(text).split())
        if cleaned:
            parts.append(cleaned)
    return " ".join(parts).strip()


def _select_and_fetch_from_list(
    transcript_list: Any,
    preferred_langs: tuple[str, ...],
    no_transcript_exc: type[Exception] = Exception,
) -> tuple[str, str, bool]:
    """Select preferred language from a TranscriptList, falling back to any available."""
    try:
        transcript = transcript_list.find_transcript(list(preferred_langs))
    except no_transcript_exc:
        transcript = next(iter(transcript_list), None)
        if transcript is None:
            raise no_transcript_exc("No transcripts found in transcript list.")

    fetched = transcript.fetch()
    text = _extract_segments_text(fetched)
    lang_code = getattr(transcript, "language_code", "") or ""
    is_generated = bool(getattr(transcript, "is_generated", False))
    return text, lang_code, is_generated


def fetch_video_transcript(
    video_id: str,
    preferred_langs: tuple[str, ...] = PREFERRED_LANGUAGES,
    api_cls: Any = None,
    no_transcript_exc: type[Exception] | None = None,
) -> tuple[str, str, bool]:
    """Fetch transcript text, language code, and auto-generated flag for a video_id.

    Compatible with both youtube-transcript-api v0.6.x and v1.x.
    """
    if api_cls is None or no_transcript_exc is None:
        loaded_cls, loaded_no_transcript, _, _ = _import_yt_api()
        api_cls = api_cls or loaded_cls
        no_transcript_exc = no_transcript_exc or loaded_no_transcript

    # v0.6.x exposes static list_transcripts/get_transcript; v1.x uses instance .list()/.fetch()
    if hasattr(api_cls, "list_transcripts"):
        try:
            transcript_list = api_cls.list_transcripts(video_id)
            return _select_and_fetch_from_list(
                transcript_list, preferred_langs, no_transcript_exc
            )
        except AttributeError:
            pass

    api = api_cls()
    if hasattr(api, "list"):
        transcript_list = api.list(video_id)
        return _select_and_fetch_from_list(
            transcript_list, preferred_langs, no_transcript_exc
        )

    if hasattr(api, "fetch"):
        fetched = api.fetch(video_id, languages=list(preferred_langs))
        lang_code = getattr(fetched, "language_code", "") or ""
        is_generated = bool(getattr(fetched, "is_generated", False))
        return _extract_segments_text(fetched), lang_code, is_generated

    if hasattr(api_cls, "get_transcript"):
        fetched = api_cls.get_transcript(
            video_id, languages=list(preferred_langs)
        )
        return _extract_segments_text(fetched), "", False

    raise RuntimeError("Unsupported youtube_transcript_api version.")


def _atomic_write_json(path: Path, payload: list[dict[str, Any]]) -> None:
    """Write JSON atomically so partial progress is never corrupted."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception looks like an HTTP 429 or YouTube IP block."""
    cls_name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return any(kw in cls_name or kw in msg for kw in RATE_LIMIT_KEYWORDS)


def _load_existing_output(
    output_path: Path,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    """Load prior output records for incremental resume and video_id reuse."""
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    by_video_id: dict[str, dict[str, Any]] = {}
    if not output_path.exists():
        return by_key, by_video_id

    try:
        existing = json.loads(output_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return by_key, by_video_id

    if not isinstance(existing, list):
        return by_key, by_video_id

    for rec in existing:
        if not isinstance(rec, dict):
            continue
        cid = str(rec.get("chassis_key", ""))
        vid = str(rec.get("video_id", ""))
        status = rec.get("status", "")
        if vid:
            by_key[(cid, vid)] = rec
            if status in ("ok", "unavailable"):
                by_video_id[vid] = rec
    return by_key, by_video_id


def run_batch(
    batch_num: int,
    input_path: Path,
    output_path: Path,
    min_sleep: float,
    max_sleep: float,
) -> int:
    """Process a batch JSON file incrementally with sleep and rate-limit protection."""
    try:
        api_cls, no_transcript_exc, disabled_exc, unavailable_exc = _import_yt_api()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if not input_path.exists():
        print(f"[ERROR] Input batch file not found: {input_path}", file=sys.stderr)
        return 1

    batch_items = json.loads(input_path.read_text(encoding="utf-8"))
    total = len(batch_items)
    existing_by_key, cached_by_vid = _load_existing_output(output_path)

    results: list[dict[str, Any]] = []
    # Seed results order cleanly while preserving resumed records
    for item in batch_items:
        cid = str(item.get("chassis_key", ""))
        vid = str(item.get("video_id", ""))
        prior = existing_by_key.get((cid, vid))
        if prior is not None and prior.get("status") in ("ok", "unavailable"):
            results.append(prior)
        else:
            results.append(dict(item))

    fetched_count = 0
    reused_count = 0
    unavailable_count = 0
    skipped_count = 0
    made_network_call = False

    print(
        f"[Batch {batch_num}] Loaded {total} entries from {input_path.name} "
        f"-> saving to {output_path.name}"
    )

    for idx, entry in enumerate(results, start=1):
        vid = str(entry.get("video_id", "")).strip()
        model = entry.get("laptop_model") or entry.get("chassis_key", "")
        prior_status = entry.get("status")

        if prior_status in ("ok", "unavailable"):
            skipped_count += 1
            continue

        if not vid:
            entry["status"] = "unavailable"
            entry["error"] = "missing video_id"
            unavailable_count += 1
            _atomic_write_json(output_path, results)
            continue

        if vid in cached_by_vid:
            cached = cached_by_vid[vid]
            entry["transcript_text"] = cached.get("transcript_text", "")
            entry["transcript_language"] = cached.get("transcript_language", "")
            entry["is_auto_generated"] = cached.get("is_auto_generated", False)
            entry["status"] = cached.get("status", "ok")
            if cached.get("error"):
                entry["error"] = cached["error"]
            reused_count += 1
            _atomic_write_json(output_path, results)
            print(f"[{idx}/{total}] REUSED  {vid} ({model})")
            continue

        if made_network_call:
            delay = random.uniform(min_sleep, max_sleep)
            time.sleep(delay)

        made_network_call = True
        try:
            text, lang_code, is_generated = fetch_video_transcript(
                vid,
                api_cls=api_cls,
                no_transcript_exc=no_transcript_exc,
            )
            entry["transcript_text"] = text
            entry["transcript_language"] = lang_code
            entry["is_auto_generated"] = is_generated
            entry["status"] = "ok" if text else "unavailable"
            if not text:
                entry["error"] = "empty transcript returned"
                unavailable_count += 1
                print(f"[{idx}/{total}] EMPTY   {vid} ({model})")
            else:
                fetched_count += 1
                print(
                    f"[{idx}/{total}] OK      {vid} [{lang_code}] "
                    f"{len(text)} chars ({model})"
                )
            cached_by_vid[vid] = entry
            _atomic_write_json(output_path, results)

        except (disabled_exc, no_transcript_exc, unavailable_exc) as exc:
            entry["transcript_text"] = ""
            entry["status"] = "unavailable"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            cached_by_vid[vid] = entry
            unavailable_count += 1
            _atomic_write_json(output_path, results)
            print(f"[{idx}/{total}] NO_SUBS {vid} ({type(exc).__name__})")

        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            _atomic_write_json(output_path, results)
            if _is_rate_limit_error(exc):
                print(
                    f"\n[RATE LIMIT] Stopped cleanly at [{idx}/{total}] ({vid}): {exc}\n"
                    f"Progress saved to {output_path}. Re-run the same command later or from another IP to resume.",
                    file=sys.stderr,
                )
                return 2
            print(f"[{idx}/{total}] ERROR   {vid} ({type(exc).__name__}: {exc})")

    print(
        f"\n[Batch {batch_num} Done] total={total}, skipped_existing={skipped_count}, "
        f"fetched={fetched_count}, reused={reused_count}, unavailable={unavailable_count}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch YouTube transcripts for a split batch file (1, 2, or 3)."
    )
    parser.add_argument(
        "--batch",
        type=int,
        required=True,
        choices=[1, 2, 3],
        help="Batch number to process (1, 2, or 3).",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Optional input JSON path (defaults to yt_batch_<batch>.json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output JSON path (defaults to yt_transcripts_out_<batch>.json).",
    )
    parser.add_argument(
        "--min-sleep",
        type=float,
        default=2.5,
        help="Minimum random delay in seconds between YouTube requests (default: 2.5).",
    )
    parser.add_argument(
        "--max-sleep",
        type=float,
        default=4.5,
        help="Maximum random delay in seconds between YouTube requests (default: 4.5).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.min_sleep < 0 or args.max_sleep < args.min_sleep:
        print("[ERROR] Invalid sleep range.", file=sys.stderr)
        return 1

    input_path = args.input or Path(f"yt_batch_{args.batch}.json")
    output_path = args.output or Path(f"yt_transcripts_out_{args.batch}.json")
    return run_batch(
        batch_num=args.batch,
        input_path=input_path,
        output_path=output_path,
        min_sleep=args.min_sleep,
        max_sleep=args.max_sleep,
    )


if __name__ == "__main__":
    raise SystemExit(main())
