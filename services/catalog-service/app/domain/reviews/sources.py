"""Pure domain normalization and extraction for laptop review source links.

Zero SQLAlchemy, FastAPI, or network imports: converts Format A (raw/v6 JSON),
Format B2 (enriched/deduplicated JSON), ORM objects, or chunk fallbacks into
deduplicated, deterministically sorted ``ReviewSourceItem`` records.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import math
from typing import Any


_SOURCE_TYPE_ORDER: dict[str, int] = {
    "editorial": 0,
    "youtube": 1,
    "community": 2,
}


@dataclass(frozen=True)
class ReviewSourceItem:
    """Normalized metadata for a single external YouTube, community, or editorial review."""

    source_type: str
    platform: str
    title: str
    url: str
    author_or_channel: str | None = None
    channel_url: str | None = None
    rating: float | None = None
    score_or_views: int | None = None
    published_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the canonical dictionary contract shared with repositories and schemas."""
        return asdict(self)


def clean_http_url(raw: Any) -> str | None:
    """Return stripped URL if it uses http(s), otherwise None."""
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    low = cleaned.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return cleaned
    return None


def _coerce_optional_int(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _coerce_optional_float(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        val = float(raw)
        return val if math.isfinite(val) else None
    except (TypeError, ValueError):
        return None


def _coerce_optional_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _clean_text(raw: Any, fallback: str = "", max_length: int | None = None) -> str:
    text = str(raw).strip() if raw is not None else ""
    if not text:
        text = fallback
    if max_length is not None and len(text) > max_length:
        return text[:max_length].rstrip()
    return text


def _normalize_source_type(raw: Any) -> str:
    val = str(raw or "").strip().lower()
    if val in _SOURCE_TYPE_ORDER:
        return val
    if "youtube" in val:
        return "youtube"
    if "editorial" in val:
        return "editorial"
    return "community"


def _build_item(
    *,
    source_type: Any,
    platform: Any,
    title: Any,
    url: Any,
    author_or_channel: Any = None,
    channel_url: Any = None,
    rating: Any = None,
    score_or_views: Any = None,
    published_at: Any = None,
) -> ReviewSourceItem | None:
    clean_url = clean_http_url(url)
    if not clean_url:
        return None

    norm_type = _normalize_source_type(source_type)
    norm_platform = _clean_text(platform, fallback=norm_type, max_length=50).lower()
    norm_title = _clean_text(title, fallback=f"{norm_platform} review")
    author_str = _clean_text(author_or_channel, max_length=150) or None

    return ReviewSourceItem(
        source_type=norm_type,
        platform=norm_platform,
        title=norm_title,
        url=clean_url,
        author_or_channel=author_str,
        channel_url=clean_http_url(channel_url),
        rating=_coerce_optional_float(rating),
        score_or_views=_coerce_optional_int(score_or_views),
        published_at=_coerce_optional_datetime(published_at),
    )


def _source_from_any(raw: Any) -> ReviewSourceItem | None:
    if isinstance(raw, ReviewSourceItem):
        return raw
    if isinstance(raw, Mapping):
        return _build_item(
            source_type=raw.get("source_type"),
            platform=raw.get("platform"),
            title=raw.get("title"),
            url=raw.get("url"),
            author_or_channel=raw.get("author_or_channel"),
            channel_url=raw.get("channel_url"),
            rating=raw.get("rating"),
            score_or_views=raw.get("score_or_views"),
            published_at=raw.get("published_at"),
        )
    # ORM model or duck-typed object
    url = getattr(raw, "url", None)
    if url is None:
        return None
    return _build_item(
        source_type=getattr(raw, "source_type", None),
        platform=getattr(raw, "platform", None),
        title=getattr(raw, "title", None),
        url=url,
        author_or_channel=getattr(raw, "author_or_channel", None),
        channel_url=getattr(raw, "channel_url", None),
        rating=getattr(raw, "rating", None),
        score_or_views=getattr(raw, "score_or_views", None),
        published_at=getattr(raw, "published_at", None),
    )


def sort_and_deduplicate_sources(items: Iterable[ReviewSourceItem]) -> list[ReviewSourceItem]:
    """Deduplicate by normalized URL and sort by editorial -> youtube -> community."""
    by_url: dict[str, ReviewSourceItem] = {}
    for item in items:
        dedup_key = item.url.rstrip("/").lower()
        if dedup_key not in by_url:
            by_url[dedup_key] = item

    return sorted(
        by_url.values(),
        key=lambda s: (
            _SOURCE_TYPE_ORDER.get(s.source_type, 3),
            -(s.score_or_views or 0),
            s.title,
        ),
    )


def normalize_review_sources_collection(raw_sources: Iterable[Any] | None) -> list[ReviewSourceItem]:
    """Normalize arbitrary dicts, dataclasses, or ORM objects into ordered ``ReviewSourceItem`` entries."""
    if not raw_sources:
        return []
    parsed: list[ReviewSourceItem] = []
    for raw in raw_sources:
        item = _source_from_any(raw)
        if item is not None:
            parsed.append(item)
    return sort_and_deduplicate_sources(parsed)


def extract_review_sources(item: Mapping[str, Any]) -> list[ReviewSourceItem]:
    """Extract normalized review sources from Format A (raw/v6) or Format B2 (enriched) chassis items."""
    collected: list[ReviewSourceItem] = []

    # 1. Pre-normalized `review_sources` (Format B2 or community_reviews)
    for raw in item.get("review_sources") or []:
        parsed = _source_from_any(raw)
        if parsed is not None:
            collected.append(parsed)

    # 2. Format A YouTube videos
    yt = item.get("youtube") if isinstance(item.get("youtube"), Mapping) else {}
    for vid in yt.get("videos") or []:
        if not isinstance(vid, Mapping):
            continue
        channel_name = _clean_text(vid.get("channel_name"), max_length=150) or None
        parsed = _build_item(
            source_type="youtube",
            platform="youtube",
            title=vid.get("title") or channel_name or "YouTube Review",
            url=vid.get("video_url"),
            author_or_channel=channel_name,
            channel_url=vid.get("channel_url"),
            score_or_views=vid.get("view_count"),
            published_at=vid.get("published_at"),
        )
        if parsed is not None:
            collected.append(parsed)

    # 3. Format A Community & Editorial buckets
    comm = item.get("communities") if isinstance(item.get("communities"), Mapping) else {}
    for ed in comm.get("editorial") or []:
        if not isinstance(ed, Mapping):
            continue
        source_name = _clean_text(ed.get("source"), fallback="editorial", max_length=150)
        parsed = _build_item(
            source_type="editorial",
            platform=source_name,
            title=ed.get("verdict") or f"{source_name} Review",
            url=ed.get("review_url"),
            author_or_channel=source_name,
            rating=ed.get("rating"),
        )
        if parsed is not None:
            collected.append(parsed)

    for bucket in ("discussions", "reddit", "facebook"):
        for post in comm.get(bucket) or []:
            if not isinstance(post, Mapping):
                continue
            default_plat = bucket if bucket != "discussions" else "community"
            platform = _clean_text(post.get("platform"), fallback=default_plat, max_length=50)
            parsed = _build_item(
                source_type="community",
                platform=platform,
                title=post.get("post_title") or post.get("title") or f"{platform} Discussion",
                url=post.get("post_url") or post.get("url"),
                author_or_channel=post.get("author"),
                score_or_views=post.get("score"),
                published_at=post.get("published_at"),
            )
            if parsed is not None:
                collected.append(parsed)

    # 4. Chunk URL fallback (only if neither pre-normalized nor raw buckets yielded any URLs)
    if not collected:
        for chunk in item.get("deduplicated_chunks") or []:
            if not isinstance(chunk, Mapping):
                continue
            url = chunk.get("source_url")
            if not url:
                continue
            chunk_type = str(chunk.get("source_type") or "").lower()
            if "youtube" in chunk_type:
                stype = "youtube"
                plat = "youtube"
            elif "editorial" in chunk_type:
                stype = "editorial"
                plat = "editorial"
            else:
                stype = "community"
                plat = "community"
            parsed = _build_item(
                source_type=stype,
                platform=plat,
                title=f"{plat.capitalize()} Review",
                url=url,
            )
            if parsed is not None:
                collected.append(parsed)

    return sort_and_deduplicate_sources(collected)


__all__ = [
    "ReviewSourceItem",
    "clean_http_url",
    "extract_review_sources",
    "normalize_review_sources_collection",
    "sort_and_deduplicate_sources",
]
