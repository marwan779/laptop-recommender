"""Injected HTTP client plumbing shared by community platform scrapers.

Keeps transport concerns (client lifecycle, timeouts, fail-open GETs) in one
place so each platform scraper only owns its URL shape and parsing rules.
Every helper is fail-open: transport and HTTP errors yield ``None`` rather than
raising into the collector.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("scraper.services.reviews.community.http")

DEFAULT_USER_AGENT = "laptop-recommender/1.0 (community review collector; contact: ops@laptop-recommender.local)"


class HttpClientContext:
    """Async context manager yielding an injected or self-owned HTTP client.

    An injected client is borrowed, never closed — the caller owns its lifecycle.
    """

    def __init__(self, injected: Any | None, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._injected = injected
        self._user_agent = user_agent
        self._owned: Any | None = None

    async def __aenter__(self) -> Any:
        if self._injected is not None:
            return self._injected

        import httpx  # noqa: PLC0415 - optional at import time

        self._owned = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
            headers={"User-Agent": self._user_agent},
        )
        return self._owned

    async def __aexit__(self, *exc_info: Any) -> bool:
        if self._owned is not None:
            await self._owned.aclose()
            self._owned = None
        return False


async def get_text(client: Any, url: str) -> str | None:
    """GET a URL and return its body text, or ``None`` on any failure."""
    try:
        response = await client.get(url)
    except Exception as exc:  # noqa: BLE001 - network failures are expected
        logger.debug("Request failed for %s: %s", url, exc)
        return None

    status = getattr(response, "status_code", 200)
    if status >= 400:
        logger.debug("HTTP %s for %s", status, url)
        return None

    try:
        return response.text
    except Exception as exc:  # noqa: BLE001 - malformed response object
        logger.debug("Response body unavailable for %s: %s", url, exc)
        return None


async def get_json(client: Any, url: str) -> Any:
    """GET a JSON payload, or ``None`` on any failure."""
    try:
        response = await client.get(url)
    except Exception as exc:  # noqa: BLE001 - network failures are expected
        logger.debug("Request failed for %s: %s", url, exc)
        return None

    status = getattr(response, "status_code", 200)
    if status >= 400:
        logger.debug("HTTP %s for %s", status, url)
        return None

    try:
        return response.json()
    except Exception as exc:  # noqa: BLE001 - malformed payload
        logger.debug("Invalid JSON for %s: %s", url, exc)
        return None


__all__ = ["DEFAULT_USER_AGENT", "HttpClientContext", "get_json", "get_text"]
