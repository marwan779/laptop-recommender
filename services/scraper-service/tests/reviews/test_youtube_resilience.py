"""Unit tests for cookieless YouTube search, deduplication, cooldowns, and subtitles."""

from __future__ import annotations

from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import YouTubeComment
from app.services.reviews.youtube.collector import YouTubeReviewsCollector
from app.services.reviews.youtube.search import YouTubeSearchService, _normalize_comment_timestamp
from app.services.reviews.youtube.transcript import TRANSCRIPT_LANGUAGES, YouTubeTranscriptService


def _target(model: str, canonical_id: str, screen_size: float = 15.6) -> LaptopReviewTarget:
    return LaptopReviewTarget(
        laptop_id=f"lap-{canonical_id}",
        canonical_id=canonical_id,
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model=model,
        screen_size=screen_size,
    )


def test_personal_cookie_module_removed():
    cookies_path = Path(__file__).resolve().parents[2] / "app" / "services" / "reviews" / "youtube" / "cookies.py"
    assert not cookies_path.exists()


def test_youtube_services_pass_no_cookiefile_to_ytdlp():
    captured_opts: list[dict] = []

    class FakeYDL:
        def __init__(self, opts):
            captured_opts.append(dict(opts))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, target, download=False):
            return {"entries": [], "comments": [], "subtitles": {}, "automatic_captions": {}}

    fake_yt_dlp = SimpleNamespace(YoutubeDL=FakeYDL)
    search_svc = YouTubeSearchService(jitter_range=(0.0, 0.0))
    transcript_svc = YouTubeTranscriptService(jitter_range=(0.0, 0.0))

    with (
        patch("app.services.reviews.youtube.search._import_yt_dlp", return_value=fake_yt_dlp),
        patch.dict("sys.modules", {"yt_dlp": fake_yt_dlp}),
    ):
        search_svc._search_sync("Lenovo LOQ 15IRX9 review")
        search_svc._fetch_top_comments_sync("https://www.youtube.com/watch?v=abc", 5)
        transcript_svc._fetch_via_ytdlp("abc")

    assert len(captured_opts) == 3
    for opts in captured_opts:
        assert "cookiefile" not in opts


def test_transcript_service_parses_json3_subtitles():
    service = YouTubeTranscriptService(jitter_range=(0.0, 0.0))

    sample_json3 = {
        "events": [
            {
                "tStartMs": 1500,
                "dDurationMs": 2000,
                "segs": [{"utf8": "Welcome to "}, {"utf8": "the laptop review."}],
            },
            {
                "tStartMs": 4000,
                "dDurationMs": 1500,
                "segs": [{"utf8": "Great build quality."}],
            },
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_json3

    with patch("requests.Session.get", return_value=mock_resp):
        track = [{"ext": "json3", "url": "https://www.youtube.com/api/timedtext?test=1"}]
        segments = service._parse_subtitle_entries(track)

    assert len(segments) == 2
    assert segments[0].start_seconds == 1.5
    assert segments[0].text == "Welcome to the laptop review."
    assert segments[1].start_seconds == 4.0
    assert segments[1].text == "Great build quality."


def test_ytdlp_fallback_picks_manual_and_preserves_language_and_auto_flag():
    service = YouTubeTranscriptService(jitter_range=(0.0, 0.0))
    info = {
        "subtitles": {
            "en-GB": [{"text": "British human captions.", "start": 1.0}],
        },
        "automatic_captions": {
            "en": [{"text": "Auto captions.", "start": 1.0}],
        },
    }

    class FakeYDL:
        def __init__(self, opts):
            assert opts["subtitleslangs"] == list(TRANSCRIPT_LANGUAGES)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            return info

    fake_yt_dlp = SimpleNamespace(YoutubeDL=FakeYDL)
    with patch.dict("sys.modules", {"yt_dlp": fake_yt_dlp}):
        result = service._fetch_via_ytdlp("vid123")

    assert result is not None
    full_text, segments, language, is_auto = result
    assert full_text == "British human captions."
    assert language == "en-GB"
    assert is_auto is False
    assert len(segments) == 1


@pytest.mark.anyio
async def test_youtube_transcript_cooldown_recovers_and_ignores_per_video_disabled():
    service = YouTubeTranscriptService(base_cooldown_seconds=0.05, jitter_range=(0.0, 0.0))

    class IpBlockedError(Exception):
        pass

    class TranscriptsDisabled(Exception):
        pass

    api_mock = MagicMock()
    # 1. Per-video TranscriptsDisabled must NOT trip session cooldown.
    api_mock.fetch.side_effect = TranscriptsDisabled("Subtitles are disabled for this video")
    fake_api_cls = MagicMock(return_value=api_mock)

    with (
        patch.dict("sys.modules", {"youtube_transcript_api": SimpleNamespace(YouTubeTranscriptApi=fake_api_cls)}),
        patch.object(service, "_fetch_via_ytdlp", return_value=None),
    ):
        await service.fetch_transcript("vid-disabled")
        assert service._ip_blocked is False

        # 2. IpBlocked trips temporary cooldown, NOT a permanent latch.
        api_mock.fetch.side_effect = IpBlockedError("YouTube is blocking requests from your IP")
        await service.fetch_transcript("vid-blocked")
        assert service._ip_blocked is True

        # Wait past short cooldown window; next video runs and succeeds.
        time.sleep(0.08)
        assert service._ip_blocked is False
        api_mock.fetch.side_effect = None
        api_mock.fetch.return_value = [{"text": "Recovered transcript.", "start": 0.5}]
        text, _, _, _ = await service.fetch_transcript("vid-recovered")
        assert text == "Recovered transcript."


def test_youtube_comments_cooldown_recovers_and_normalizes_timestamps():
    assert _normalize_comment_timestamp({"timestamp": 1700000000}) == "2023-11-14T22:13:20Z"
    assert _normalize_comment_timestamp({"published_at": "2026-01-02T00:00:00Z"}) == "2026-01-02T00:00:00Z"

    svc = YouTubeSearchService(base_cooldown_seconds=0.05, jitter_range=(0.0, 0.0))
    svc._trip_comments_cooldown("HTTP 403 Forbidden")
    assert svc._comments_blocked is True
    time.sleep(0.08)
    assert svc._comments_blocked is False


@pytest.mark.anyio
async def test_youtube_collector_deduplicates_queries_comments_and_filters_irrelevant():
    shared_relevant = {
        "video_id": "vid-loq",
        "title": "Lenovo LOQ 15IRX9 Review - Worth Buying?",
        "channel_name": "TechLab",
        "video_url": "https://www.youtube.com/watch?v=vid-loq",
        "duration_seconds": 600,
        "comments_deferred": True,
    }
    accessory_video = {
        "video_id": "vid-bag",
        "title": "Lenovo LOQ Backpack & Sleeve Review",
        "channel_name": "Gear",
        "video_url": "https://www.youtube.com/watch?v=vid-bag",
        "duration_seconds": 300,
        "comments_deferred": True,
    }
    wrong_brand = {
        "video_id": "vid-asus",
        "title": "ASUS TUF Gaming A15 Review",
        "channel_name": "TechLab",
        "video_url": "https://www.youtube.com/watch?v=vid-asus",
        "duration_seconds": 600,
        "comments_deferred": True,
    }

    search_service = AsyncMock()
    search_service.search_reviews = AsyncMock(return_value=[shared_relevant, accessory_video, wrong_brand])
    search_service.fetch_top_comments = AsyncMock(
        return_value=[YouTubeComment(comment_id="c1", comment_text="Solid thermals!")]
    )

    transcript_service = AsyncMock()
    transcript_service.fetch_transcript = AsyncMock(return_value=("Transcript body", [], "en", False))

    collector = YouTubeReviewsCollector(
        search_service=search_service,
        transcript_service=transcript_service,
    )

    # Identical model/family queries share both search results and hydrated video fetches.
    t1 = _target("LOQ 15IRX9", "canon-1")
    t2 = _target("LOQ 15IRX9", "canon-2").model_copy(update={"chassis_key": "lenovo:loq:15IRX9-b"})

    results = await collector.collect_for_targets([t1, t2])

    # Search runs once for primary query + once for secondary query (since only 1 video passed filter < 2).
    assert search_service.search_reviews.await_count == 2
    # Deferred comments AND transcripts execute strictly once for vid-loq, zero times for filtered videos.
    transcript_service.fetch_transcript.assert_awaited_once_with("vid-loq")
    search_service.fetch_top_comments.assert_awaited_once_with("https://www.youtube.com/watch?v=vid-loq")

    for data in results.values():
        assert [v.video_id for v in data.videos] == ["vid-loq"]
        assert data.videos[0].top_comments[0].comment_id == "c1"
        assert " | " in data.query_used
