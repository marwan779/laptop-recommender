"""YouTube transcript retrieval with graceful fallbacks.

Strategy:
    1. ``youtube-transcript-api`` (fast, no browser, handles auto-captions).
    2. yt-dlp automatic subtitles (handles cases the API cannot).
    3. Fail-open: return ``("", [], "en", False)`` so one bad video never aborts
       the batch.

Both libraries are imported lazily so the module (and the collector) stay
importable and unit-testable when they are not installed.
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from typing import Any

from app.schemas.reviews_s3 import TranscriptSegment

logger = logging.getLogger("scraper.services.reviews.youtube.transcript")

# Languages tried, in priority order.
TRANSCRIPT_LANGUAGES: tuple[str, ...] = ("en", "en-US", "en-GB", "en-orig", "ar", "ar-EG", "ar-SA")

# Fallback return value when no transcript can be obtained.
EMPTY_TRANSCRIPT: tuple[str, list[TranscriptSegment], str, bool] = ("", [], "en", False)

_MAX_COOLDOWN_SECONDS = 300.0
_DEFAULT_JITTER_RANGE: tuple[float, float] = (0.15, 0.45)
_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}


def _is_ip_rate_limit(exc: Exception) -> bool:
    name = type(exc).__name__
    msg = str(exc).lower()
    if any(tok in name for tok in ("IpBlocked", "RequestBlocked", "TooManyRequests")):
        return True
    return any(
        marker in msg
        for marker in (
            "blocking requests from your ip",
            "429",
            "too many requests",
            "403",
            "forbidden",
        )
    )


class YouTubeTranscriptService:
    """Fetch captions for a YouTube video without personal cookies.

    Uses a reusable cookieless ``requests.Session`` for HTTP connection pooling
    and a timed cooldown circuit breaker that recovers automatically instead of
    permanently aborting the remainder of a batch.
    """

    def __init__(
        self,
        languages: tuple[str, ...] = TRANSCRIPT_LANGUAGES,
        base_cooldown_seconds: float = 30.0,
        jitter_range: tuple[float, float] = _DEFAULT_JITTER_RANGE,
    ) -> None:
        self.languages = languages
        self.base_cooldown_seconds = base_cooldown_seconds
        self.jitter_range = jitter_range

        self._lock = threading.Lock()
        self._session: Any | None = None
        self._cooldown_until: float = 0.0
        self._failure_streak: int = 0

    @property
    def _ip_blocked(self) -> bool:
        """Backward-compatible cooldown inspection property."""
        return self._is_in_cooldown()

    def _is_in_cooldown(self) -> bool:
        with self._lock:
            return time.monotonic() < self._cooldown_until

    def _trip_cooldown(self, reason: str = "") -> None:
        with self._lock:
            self._failure_streak += 1
            delay = min(
                self.base_cooldown_seconds * (2 ** (self._failure_streak - 1)),
                _MAX_COOLDOWN_SECONDS,
            )
            now = time.monotonic()
            was_cooling = now < self._cooldown_until
            self._cooldown_until = now + delay
            if not was_cooling:
                logger.warning(
                    "YouTube transcript endpoint rate-limited (%s). Entering %.1fs cooldown.",
                    reason or "IpBlocked/429",
                    delay,
                )

    def _reset_cooldown(self) -> None:
        with self._lock:
            self._failure_streak = 0
            self._cooldown_until = 0.0

    def _get_http_session(self) -> Any | None:
        """Return a shared cookieless ``requests.Session`` with connection pooling."""
        with self._lock:
            if self._session is not None:
                return self._session
            try:
                import requests  # noqa: PLC0415
                from requests.adapters import HTTPAdapter  # noqa: PLC0415
            except ImportError:  # pragma: no cover
                return None

            session = requests.Session()
            adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            session.headers.update(_DEFAULT_HEADERS)
            self._session = session
            return self._session

    async def _pace(self) -> None:
        low, high = self.jitter_range
        if high > 0 and high >= low:
            await asyncio.sleep(random.uniform(max(0.0, low), high))

    async def fetch_transcript(
        self,
        video_id: str,
    ) -> tuple[str, list[TranscriptSegment], str, bool]:
        """Return ``(transcript_text, segments, language, is_auto_generated)``.

        Never raises: returns :data:`EMPTY_TRANSCRIPT` when every strategy fails.
        """
        if not video_id or self._is_in_cooldown():
            return EMPTY_TRANSCRIPT

        await self._pace()
        result = await asyncio.to_thread(self._fetch_sync, video_id)
        return result

    # ── Internal synchronous implementation (runs in a worker thread) ──────

    def _fetch_sync(self, video_id: str) -> tuple[str, list[TranscriptSegment], str, bool]:
        if self._is_in_cooldown():
            return EMPTY_TRANSCRIPT

        primary = self._fetch_via_api(video_id)
        if primary is not None:
            self._reset_cooldown()
            return primary

        if self._is_in_cooldown():
            return EMPTY_TRANSCRIPT

        fallback = self._fetch_via_ytdlp(video_id)
        if fallback is not None:
            self._reset_cooldown()
            return fallback

        return EMPTY_TRANSCRIPT

    def _fetch_via_api(
        self,
        video_id: str,
    ) -> tuple[str, list[TranscriptSegment], str, bool] | None:
        """Primary strategy: youtube-transcript-api."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi  # noqa: PLC0415
        except ImportError:  # pragma: no cover - environment dependent
            return None

        try:
            session = self._get_http_session()
            api = YouTubeTranscriptApi(http_client=session) if session else YouTubeTranscriptApi()
            fetched = api.fetch(video_id, languages=list(self.languages))
        except Exception as exc:  # noqa: BLE001 - TranscriptsDisabled / NoTranscriptFound / network
            if _is_ip_rate_limit(exc):
                self._trip_cooldown(str(exc))
            logger.debug("Transcript API failed for %s: %s", video_id, exc)
            return None

        raw_segments = self._raw_segments(fetched)
        if not raw_segments:
            return None

        segments = [
            TranscriptSegment(
                start_seconds=float(entry.get("start", 0.0)),
                text=str(entry.get("text", "")).strip(),
            )
            for entry in raw_segments
            if str(entry.get("text", "")).strip()
        ]
        if not segments:
            return None

        language = self._detected_language(fetched) or self.languages[0]
        is_auto = bool(getattr(fetched, "is_generated", False))

        return self._build_result(segments, language, is_auto)

    def _fetch_via_ytdlp(
        self,
        video_id: str,
    ) -> tuple[str, list[TranscriptSegment], str, bool] | None:
        """Fallback strategy: yt-dlp manual & automatic subtitles."""
        try:
            import yt_dlp  # noqa: PLC0415
        except ImportError:  # pragma: no cover - environment dependent
            return None

        opts: dict[str, Any] = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": list(self.languages),
            "subtitlesformat": "json3/vtt/best",
            "format": "all",
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "noprogress": True,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False,
                )
        except Exception as exc:  # noqa: BLE001 - subtitle extraction is best-effort
            if _is_ip_rate_limit(exc):
                self._trip_cooldown(str(exc))
            logger.debug("yt-dlp subtitle fallback failed for %s: %s", video_id, exc)
            return None

        picked = self._pick_subtitle_track(info or {}, self.languages)
        if picked is None:
            return None

        track, chosen_language, is_auto = picked
        segments = self._parse_subtitle_entries(track)
        if not segments:
            return None

        return self._build_result(segments, chosen_language, is_auto)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _raw_segments(fetched: Any) -> list[dict[str, Any]]:
        """Normalize a ``FetchedTranscript`` (v1.x) or list-of-dicts (v0.x)."""
        if fetched is None:
            return []

        # v1.x: FetchedTranscript exposes to_raw_data().
        to_raw = getattr(fetched, "to_raw_data", None)
        if callable(to_raw):
            try:
                return list(to_raw())
            except Exception:  # noqa: BLE001
                return []

        # v0.x: list of dicts / snippet objects.
        if isinstance(fetched, list):
            normalized: list[dict[str, Any]] = []
            for entry in fetched:
                if isinstance(entry, dict):
                    normalized.append(entry)
                else:
                    normalized.append(
                        {
                            "text": getattr(entry, "text", ""),
                            "start": getattr(entry, "start", 0.0),
                        }
                    )
            return normalized

        return []

    @staticmethod
    def _detected_language(fetched: Any) -> str | None:
        language = getattr(fetched, "language_code", None) or getattr(fetched, "language", None)
        return str(language) if language else None

    @staticmethod
    def _pick_subtitle_track(
        info: dict[str, Any],
        preferred_languages: tuple[str, ...] = TRANSCRIPT_LANGUAGES,
    ) -> tuple[Any, str, bool] | None:
        """Choose a subtitle track and return ``(track, language_code, is_auto)``.

        Prefers manual ``subtitles`` (``is_auto=False``) over ``automatic_captions``
        (``is_auto=True``), checking exact language matches first and prefix
        matches (e.g. ``en-US``, ``en-orig``, ``ar-EG``) second.
        """
        for key, is_auto in (("subtitles", False), ("automatic_captions", True)):
            tracks = info.get(key) or {}
            if not isinstance(tracks, dict):
                continue

            # 1. Exact priority match
            for lang in preferred_languages:
                if lang in tracks and tracks[lang]:
                    return tracks[lang], lang, is_auto

            # 2. Language-family prefix match (e.g. en -> en-US / en-orig, ar -> ar-EG)
            bases = tuple({lang.split("-")[0].lower() for lang in preferred_languages if lang})
            for track_lang, track in tracks.items():
                if not track:
                    continue
                lower_lang = str(track_lang).lower()
                if any(lower_lang == b or lower_lang.startswith(f"{b}-") for b in bases):
                    return track, str(track_lang), is_auto

            # 3. Any available non-empty track
            for track_lang, track in tracks.items():
                if track:
                    return track, str(track_lang), is_auto
        return None

    def _parse_subtitle_entries(self, track: Any) -> list[TranscriptSegment]:
        """Parse yt-dlp subtitle metadata into transcript segments."""
        if not isinstance(track, list):
            return []

        # Strategy 1: Pre-parsed segment text dictionaries
        segments: list[TranscriptSegment] = []
        for item in track:
            if not isinstance(item, dict):
                continue
            # yt-dlp usually exposes a "data" string plus ext; text is optional.
            text = item.get("text") or item.get("data")
            if not text:
                continue
            start = item.get("start") or item.get("start_time") or 0.0
            try:
                start_seconds = float(start)
            except (TypeError, ValueError):
                start_seconds = 0.0
            segments.append(TranscriptSegment(start_seconds=start_seconds, text=str(text).strip()))

        if segments:
            return segments

        # Strategy 2: Format descriptors containing signed URLs (e.g. json3)
        for item in track:
            if not isinstance(item, dict):
                continue
            if item.get("ext") == "json3" and item.get("url"):
                json_segs = self._fetch_json3_segments(item["url"])
                if json_segs:
                    return json_segs

        return []

    def _fetch_json3_segments(self, url: str) -> list[TranscriptSegment]:
        """Fetch and parse signed json3 subtitle events."""
        try:
            session = self._get_http_session()
            if session is None:
                return []
            resp = session.get(url, timeout=10)
            if resp.status_code != 200:
                return []
            data = resp.json()
            events = data.get("events") or []
            segments: list[TranscriptSegment] = []
            for ev in events:
                start_ms = ev.get("tStartMs", 0)
                segs = ev.get("segs", [])
                text = "".join(s.get("utf8", "") for s in segs if isinstance(s, dict)).strip()
                if text and text != "\n":
                    segments.append(
                        TranscriptSegment(
                            start_seconds=round(float(start_ms) / 1000.0, 3),
                            text=text,
                        )
                    )
            return segments
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to fetch or parse json3 subtitles from %s: %s", url, exc)
            return []

    @staticmethod
    def _build_result(
        segments: list[TranscriptSegment],
        language: str,
        is_auto: bool,
    ) -> tuple[str, list[TranscriptSegment], str, bool]:
        full_text = " ".join(segment.text for segment in segments).strip()
        return full_text, segments, language, is_auto


__all__ = ["EMPTY_TRANSCRIPT", "TRANSCRIPT_LANGUAGES", "YouTubeTranscriptService"]
