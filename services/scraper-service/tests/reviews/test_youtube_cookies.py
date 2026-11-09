"""Unit tests for YouTube cookie resolution and authentication integration."""

import os
from unittest.mock import MagicMock, patch

import pytest
from app.schemas.reviews_s3 import TranscriptSegment
from app.services.reviews.youtube.cookies import (
    build_authenticated_session,
    resolve_youtube_cookiefile,
)
from app.services.reviews.youtube.search import YouTubeSearchService
from app.services.reviews.youtube.transcript import YouTubeTranscriptService


def test_resolve_cookiefile_explicit_path(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    resolved = resolve_youtube_cookiefile(str(cookie_file))
    assert resolved == str(cookie_file.resolve())


def test_resolve_cookiefile_missing_returns_none(tmp_path):
    non_existent = str(tmp_path / "missing.txt")
    with patch.dict(os.environ, {}, clear=True):
        # Explicit non-existent path
        assert resolve_youtube_cookiefile(non_existent) is None


def test_resolve_cookiefile_from_env(tmp_path):
    cookie_file = tmp_path / "env_cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    with patch.dict(os.environ, {"YOUTUBE_COOKIES_FILE": str(cookie_file)}):
        assert resolve_youtube_cookiefile() == str(cookie_file.resolve())


def test_build_authenticated_session_creates_session_with_cookies(tmp_path):
    cookie_file = tmp_path / "test_cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tTEST_COOKIE\ttest_val\n"
    )
    session = build_authenticated_session(str(cookie_file))
    assert session is not None
    assert any(c.name == "TEST_COOKIE" and c.value == "test_val" for c in session.cookies)
    assert "User-Agent" in session.headers
    assert "Mozilla" in session.headers["User-Agent"]


def test_build_authenticated_session_returns_none_when_no_file():
    session = build_authenticated_session("non_existent_file.txt")
    assert session is None


def test_transcript_service_initializes_with_cookies(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    service = YouTubeTranscriptService(cookiefile=str(cookie_file))
    assert service.cookiefile == str(cookie_file.resolve())


def test_transcript_service_parses_json3_subtitles(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    service = YouTubeTranscriptService(cookiefile=str(cookie_file))

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


def test_search_service_initializes_with_cookies(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    service = YouTubeSearchService(cookiefile=str(cookie_file))
    assert service.cookiefile == str(cookie_file.resolve())
