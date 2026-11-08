"""Arabhardware regional community/editorial scraper.

Flow:
    1. ``GET https://arabhardware.net/search?q={regional_query}``
    2. Extract article and forum discussion snippets from the results page.
    3. Map each result onto a ``CommunityPost``.

Fail-open: transport, HTTP, or parsing failures return an empty list.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

from app.domain.reviews.community_queries import CommunityQueryBuilder
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import CommunityPost
from app.services.reviews.community.contracts import ICommunityPlatformScraper
from app.services.reviews.community.http import DEFAULT_USER_AGENT, HttpClientContext, get_text

logger = logging.getLogger("scraper.services.reviews.community.arabhardware")

ARABHARDWARE_BASE_URL = "https://arabhardware.net"
ARABHARDWARE_SEARCH_URL = f"{ARABHARDWARE_BASE_URL}/search?q={{query}}"

# Containers that typically wrap one search result.
_RESULT_SELECTORS: tuple[str, ...] = ("article", ".search-result", ".post", "li.result")
_SNIPPET_SELECTORS: tuple[str, ...] = (".excerpt", ".snippet", ".search-snippet", "p")
_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ArabhardwarePlatformScraper(ICommunityPlatformScraper):
    """Scrape Arabhardware for Arabic-language article and forum discussions."""

    platform_name = "arabhardware"

    def __init__(
        self,
        http_client: Any | None = None,
        query_builder: CommunityQueryBuilder | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        max_results: int = 10,
    ) -> None:
        self.http_client = http_client
        self.query_builder = query_builder or CommunityQueryBuilder()
        self.user_agent = user_agent
        self.max_results = max_results

    async def scrape_for_target(
        self,
        laptop_target: LaptopReviewTarget,
        queries: list[str],
    ) -> list[CommunityPost]:
        """Return discussion snippets for one target. Never raises."""
        query = self.query_builder.regional_query(laptop_target)
        if not query:
            return []

        try:
            async with HttpClientContext(self.http_client, self.user_agent) as client:
                url = ARABHARDWARE_SEARCH_URL.format(query=quote_plus(query))
                html = await get_text(client, url)
                if not html:
                    return []
                return self._parse_results(html)
        except Exception as exc:  # noqa: BLE001 - fail open for every failure mode
            logger.warning("Arabhardware scrape failed for '%s': %s", laptop_target.canonical_id, exc)
            return []

    # ── Result parsing ─────────────────────────────────────────────────────

    def _parse_results(self, html: str) -> list[CommunityPost]:
        from bs4 import BeautifulSoup  # noqa: PLC0415 - optional at import time

        soup = BeautifulSoup(html, "html.parser")
        posts: list[CommunityPost] = []
        seen_urls: set[str] = set()

        for container in self._result_containers(soup):
            anchor = container.select_one("h2 a[href], h3 a[href], a[href]")
            if anchor is None:
                continue

            href = str(anchor.get("href") or "").strip()
            if not href:
                continue
            absolute = urljoin(ARABHARDWARE_BASE_URL, href)
            parsed = urlparse(absolute)
            if parsed.netloc and "arabhardware.net" not in parsed.netloc:
                continue
            if absolute in seen_urls:
                continue

            title = anchor.get_text(" ", strip=True) or str(anchor.get("title") or "")
            snippet = self._extract_snippet(container, anchor)
            if not title and not snippet:
                continue

            seen_urls.add(absolute)
            posts.append(
                CommunityPost(
                    platform=self.platform_name,
                    post_id=self._post_id(parsed.path),
                    post_title=title,
                    post_url=absolute,
                    post_body=snippet,
                )
            )
            if len(posts) >= self.max_results:
                break

        return posts

    @staticmethod
    def _result_containers(soup: Any) -> list[Any]:
        for selector in _RESULT_SELECTORS:
            containers = soup.select(selector)
            if containers:
                return containers
        return [soup]

    @staticmethod
    def _extract_snippet(container: Any, anchor: Any) -> str:
        for selector in _SNIPPET_SELECTORS:
            node = container.select_one(selector)
            if node is None:
                continue
            text = _WHITESPACE_RE.sub(" ", node.get_text(" ", strip=True)).strip()
            if text and text != anchor.get_text(" ", strip=True):
                return text

        text = _WHITESPACE_RE.sub(" ", container.get_text(" ", strip=True)).strip()
        title = anchor.get_text(" ", strip=True)
        if text.startswith(title):
            text = text[len(title) :].strip()
        return text

    @staticmethod
    def _post_id(path: str) -> str:
        slug = _SLUG_RE.sub("-", (path or "").lower()).strip("-")
        return slug or "arabhardware-result"


__all__ = [
    "ARABHARDWARE_BASE_URL",
    "ARABHARDWARE_SEARCH_URL",
    "ArabhardwarePlatformScraper",
]
