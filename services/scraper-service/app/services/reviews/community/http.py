"""Injected HTTP client plumbing shared by community platform scrapers.

Keeps transport concerns (client lifecycle, timeouts, fail-open GETs) in one
place so each platform scraper only owns its URL shape and parsing rules.
Every helper is fail-open: transport and HTTP errors yield ``None`` rather than
raising into the collector.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
import logging
from typing import Any

logger = logging.getLogger("scraper.services.reviews.community.http")

DEFAULT_USER_AGENT = "laptop-recommender/1.0 (community review collector; contact: ops@laptop-recommender.local)"

_BATCH_CLIENT_VAR: ContextVar[Any | None] = ContextVar("community_batch_http_client", default=None)
_BATCH_CACHE_VAR: ContextVar[_BatchResponseCache | None] = ContextVar("community_batch_response_cache", default=None)


class _BatchResponseCache:
    """Single-flight async cache for GET text/json responses inside one batch."""

    def __init__(self) -> None:
        self._text_cache: dict[str, str | None] = {}
        self._json_cache: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, kind: str, url: str) -> asyncio.Lock:
        return self._locks.setdefault(f"{kind}:{url}", asyncio.Lock())

    def has_text(self, url: str) -> bool:
        return url in self._text_cache

    def get_text(self, url: str) -> str | None:
        return self._text_cache.get(url)

    def set_text(self, url: str, value: str | None) -> None:
        self._text_cache[url] = value

    def has_json(self, url: str) -> bool:
        return url in self._json_cache

    def get_json(self, url: str) -> Any:
        return self._json_cache.get(url)

    def set_json(self, url: str, value: Any) -> None:
        self._json_cache[url] = value


@asynccontextmanager
async def shared_community_session(user_agent: str = DEFAULT_USER_AGENT):
    """Provide one pooled ``httpx.AsyncClient`` and URL cache for a batch."""
    import httpx  # noqa: PLC0415 - optional at import time

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        headers={"User-Agent": user_agent},
    )
    cache = _BatchResponseCache()
    client_token = _BATCH_CLIENT_VAR.set(client)
    cache_token = _BATCH_CACHE_VAR.set(cache)
    try:
        yield client
    finally:
        _BATCH_CACHE_VAR.reset(cache_token)
        _BATCH_CLIENT_VAR.reset(client_token)
        await client.aclose()


class HttpClientContext:
    """Async context manager yielding an injected, batch-shared, or owned client.

    Injected and batch-shared clients are borrowed and never closed here.
    """

    def __init__(self, injected: Any | None, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._injected = injected
        self._user_agent = user_agent
        self._owned: Any | None = None

    async def __aenter__(self) -> Any:
        if self._injected is not None:
            return self._injected

        shared = _BATCH_CLIENT_VAR.get()
        if shared is not None:
            return shared

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
    """GET a URL and return its body text (cached per batch), or ``None`` on failure."""
    cache = _BATCH_CACHE_VAR.get()
    if cache is not None:
        if cache.has_text(url):
            return cache.get_text(url)
        async with cache.lock_for("text", url):
            if cache.has_text(url):
                return cache.get_text(url)
            value = await _fetch_text_uncached(client, url)
            cache.set_text(url, value)
            return value
    return await _fetch_text_uncached(client, url)


async def _fetch_text_uncached(client: Any, url: str) -> str | None:
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
    """GET a JSON payload (cached per batch), or ``None`` on failure."""
    cache = _BATCH_CACHE_VAR.get()
    if cache is not None:
        if cache.has_json(url):
            return cache.get_json(url)
        async with cache.lock_for("json", url):
            if cache.has_json(url):
                return cache.get_json(url)
            value = await _fetch_json_uncached(client, url)
            cache.set_json(url, value)
            return value
    return await _fetch_json_uncached(client, url)


async def _fetch_json_uncached(client: Any, url: str) -> Any:
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


__all__ = [
    "DEFAULT_USER_AGENT",
    "HttpClientContext",
    "get_json",
    "get_text",
    "shared_community_session",
]
