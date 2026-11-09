"""Helper utilities for resolving YouTube session cookies."""

from __future__ import annotations

import http.cookiejar
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("scraper.services.reviews.youtube.cookies")


def resolve_youtube_cookiefile(cookiefile: str | None = None) -> str | None:
    """Find an available cookies.txt file if present.

    Lookup precedence:
        1. Explicitly provided file path (if provided, must exist; no fallback).
        2. Environment variable ``YOUTUBE_COOKIES_FILE``.
        3. Relative to service directory: ``services/scraper-service/cookies.txt``.
        4. Current working directory: ``./cookies.txt`` or ``services/scraper-service/cookies.txt``.
    """
    if cookiefile is not None:
        return str(Path(cookiefile).resolve()) if os.path.isfile(cookiefile) else None

    env_path = os.environ.get("YOUTUBE_COOKIES_FILE")
    if env_path and os.path.isfile(env_path):
        return str(Path(env_path).resolve())

    # Path relative to this file:
    # cookies.py -> youtube -> reviews -> services -> app -> scraper-service
    service_root = Path(__file__).resolve().parents[4]
    candidate = service_root / "cookies.txt"
    if candidate.is_file():
        return str(candidate)

    # Repository root fallback
    repo_root = Path(__file__).resolve().parents[5]
    candidate_repo = repo_root / "services" / "scraper-service" / "cookies.txt"
    if candidate_repo.is_file():
        return str(candidate_repo)

    # Current working directory fallbacks
    cwd_candidate = Path("services/scraper-service/cookies.txt").resolve()
    if cwd_candidate.is_file():
        return str(cwd_candidate)

    cwd_direct = Path("cookies.txt").resolve()
    if cwd_direct.is_file():
        return str(cwd_direct)

    return None


def build_authenticated_session(cookiefile: str | None = None) -> Any:
    """Build a requests.Session populated with YouTube session cookies.

    Returns ``None`` if no cookie file is found or if cookie parsing fails.
    """
    resolved_path = resolve_youtube_cookiefile(cookiefile)
    if not resolved_path:
        return None

    try:
        import requests  # noqa: PLC0415

        jar = http.cookiejar.MozillaCookieJar(resolved_path)
        jar.load(ignore_discard=True, ignore_expires=True)

        session = requests.Session()
        session.cookies = jar
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.youtube.com/",
            }
        )
        logger.info("Successfully loaded YouTube cookies from %s", resolved_path)
        return session
    except Exception as exc:  # noqa: BLE001 - cookie parsing issues fail-open
        logger.warning("Failed to load YouTube cookies from %s: %s", resolved_path, exc)
        return None
