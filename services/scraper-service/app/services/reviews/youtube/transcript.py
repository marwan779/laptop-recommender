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
from typing import Any

from app.schemas.reviews_s3 import TranscriptSegment
from app.services.reviews.youtube.cookies import (
    build_authenticated_session,
    resolve_youtube_cookiefile,
)

logger = logging.getLogger("scraper.services.reviews.youtube.transcript")

# Languages tried, in priority order.
TRANSCRIPT_LANGUAGES: tuple[str, ...] = ("en", "en-US", "en-GB", "ar")

# Fallback return value when no transcript can be obtained.
EMPTY_TRANSCRIPT: tuple[str, list[TranscriptSegment], str, bool] = ("", [], "en", False)


class YouTubeTranscriptService:
    """Fetch captions for a YouTube video, preferring the transcript API."""

    def __init__(
        self,
        languages: tuple[str, ...] = TRANSCRIPT_LANGUAGES,
        cookiefile: str | None = None,
    ) -> None:
        self.languages = languages
        self.cookiefile = resolve_youtube_cookiefile(cookiefile)
        self._ip_blocked: bool = False

    async def fetch_transcript(
        self,
        video_id: str,
    ) -> tuple[str, list[TranscriptSegment], str, bool]:
        """Return ``(transcript_text, segments, language, is_auto_generated)``.

        Never raises: returns :data:`EMPTY_TRANSCRIPT` when every strategy fails.
        """
        if not video_id or self._ip_blocked:
            return EMPTY_TRANSCRIPT

        result = await asyncio.to_thread(self._fetch_sync, video_id)
        return result

    # ── Internal synchronous implementation (runs in a worker thread) ──────

    def _fetch_sync(self, video_id: str) -> tuple[str, list[TranscriptSegment], str, bool]:
        if self._ip_blocked:
            return EMPTY_TRANSCRIPT

        primary = self._fetch_via_api(video_id)
        if primary is not None:
            return primary

        if self._ip_blocked:
            return EMPTY_TRANSCRIPT

        fallback = self._fetch_via_ytdlp(video_id)
        if fallback is not None:
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
            session = build_authenticated_session(self.cookiefile)
            api = YouTubeTranscriptApi(http_client=session) if session else YouTubeTranscriptApi()
            fetched = api.fetch(video_id, languages=list(self.languages))
        except Exception as exc:  # noqa: BLE001 - TranscriptsDisabled / NoTranscriptFound / network
            exc_str = str(exc)
            if "blocking requests from your IP" in exc_str or "IpBlocked" in type(exc).__name__:
                if not self._ip_blocked:
                    logger.warning("YouTube is blocking transcript requests from this IP. Tripping circuit breaker for session.")
                self._ip_blocked = True
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
        """Fallback strategy: yt-dlp automatic subtitles."""
        try:
            import yt_dlp  # noqa: PLC0415
        except ImportError:  # pragma: no cover - environment dependent
            return None

        opts: dict[str, Any] = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "ar"],
            "subtitlesformat": "json3/vtt/best",
            "format": "all",
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "noprogress": True,
        }
        if self.cookiefile:
            opts["cookiefile"] = str(self.cookiefile)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False,
                )
        except Exception as exc:  # noqa: BLE001 - subtitle extraction is best-effort
            exc_str = str(exc)
            if "403" in exc_str or "Forbidden" in exc_str or "blocking requests from your IP" in exc_str:
                self._ip_blocked = True
            logger.debug("yt-dlp subtitle fallback failed for %s: %s", video_id, exc)
            return None

        subtitles = self._pick_subtitle_track(info or {})
        if not subtitles:
            return None

        segments = self._parse_subtitle_entries(subtitles)
        if not segments:
            return None

        return self._build_result(segments, self.languages[0], True)

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
    def _pick_subtitle_track(info: dict[str, Any]) -> Any:
        """Choose a subtitle track, preferring manual over automatic captions."""
        for key in ("subtitles", "automatic_captions"):
            tracks = info.get(key) or {}
            if not isinstance(tracks, dict):
                continue
            for lang in TRANSCRIPT_LANGUAGES:
                if lang in tracks and tracks[lang]:
                    return tracks[lang]
            # Any available language is better than nothing.
            for track in tracks.values():
                if track:
                    return track
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
            import requests  # noqa: PLC0415

            session = build_authenticated_session(self.cookiefile)
            client = session or requests.Session()
            resp = client.get(url, timeout=10)
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
