"""Laptop Mag editorial review scraper.

Flow:
    1. ``GET https://www.laptopmag.com/search?searchTerm={editorial_query}``
    2. Pick the top review result URL.
    3. Fetch the review page and extract pros, cons, verdict, and rating.

Fail-open by design: any transport, HTTP, or parsing failure returns an empty
list so an editorial outage never aborts the community collection batch.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

from app.domain.reviews.community_queries import CommunityQueryBuilder
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import EditorialReview
from app.services.reviews.community.contracts import ICommunityPlatformScraper
from app.services.reviews.community.filters import is_non_laptop_device
from app.services.reviews.community.http import DEFAULT_USER_AGENT, HttpClientContext, get_text

logger = logging.getLogger("scraper.services.reviews.community.laptopmag")

LAPTOPMAG_BASE_URL = "https://www.laptopmag.com"
LAPTOPMAG_SEARCH_URL = f"{LAPTOPMAG_BASE_URL}/search?searchTerm={{query}}"

_RATING_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:out of|/|of)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_NUMERIC_RATING_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")

# Exact URL paths that are navigation/category hubs, never an individual review article.
_NON_REVIEW_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "/reviews",
        "/reviews/",
        "/laptops/reviews",
        "/laptops/reviews/",
        "/reviews/all",
    }
)

# URL path fragments that are never an individual review article.
_NON_REVIEW_FRAGMENTS: tuple[str, ...] = (
    "/search",
    "/tag/",
    "/author/",
    "/category/",
    "/news",
    "/deals",
    "/about",
    "/contact",
    "/privacy",
)


class LaptopMagPlatformScraper(ICommunityPlatformScraper):
    """Scrape Laptop Mag for a professional editorial review of the chassis."""

    platform_name = "laptopmag"

    def __init__(
        self,
        http_client: Any | None = None,
        query_builder: CommunityQueryBuilder | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        max_results: int = 1,
    ) -> None:
        self.http_client = http_client
        self.query_builder = query_builder or CommunityQueryBuilder()
        self.user_agent = user_agent
        self.max_results = max_results

    async def scrape_for_target(
        self,
        laptop_target: LaptopReviewTarget,
        queries: list[str],
    ) -> list[EditorialReview]:
        """Return at most ``max_results`` editorial reviews. Never raises."""
        query = self.query_builder.editorial_query(laptop_target)
        if not query:
            return []

        try:
            async with HttpClientContext(self.http_client, self.user_agent) as client:
                search_url = LAPTOPMAG_SEARCH_URL.format(query=quote_plus(query))
                search_html = await get_text(client, search_url)
                if not search_html:
                    return []

                review_urls = self._extract_review_urls(search_html, laptop_target)[: self.max_results]
                reviews: list[EditorialReview] = []
                for review_url in review_urls:
                    review_html = await get_text(client, review_url)
                    if not review_html:
                        continue
                    parsed = self._parse_review(review_html, review_url)
                    # Never emit empty dummy shells
                    if parsed.rating is not None or parsed.pros or parsed.cons or parsed.verdict:
                        reviews.append(parsed)
                return reviews
        except Exception as exc:  # noqa: BLE001 - fail open for every failure mode
            logger.warning("LaptopMag scrape failed for '%s': %s", laptop_target.canonical_id, exc)
            return []

    # ── Search result parsing ───────────────────────────────────────────────

    def _extract_review_urls(self, html: str, target: LaptopReviewTarget | None = None) -> list[str]:
        """Return candidate review URLs from a search results page, in order."""
        from bs4 import BeautifulSoup  # noqa: PLC0415 - optional at import time

        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        seen: set[str] = set()

        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href") or "").strip()
            if not href:
                continue
            absolute = urljoin(LAPTOPMAG_BASE_URL, href)
            parsed = urlparse(absolute)
            if parsed.netloc and "laptopmag.com" not in parsed.netloc:
                continue
            path = parsed.path.lower()
            if not path or path == "/":
                continue
            if path in _NON_REVIEW_EXACT_PATHS:
                continue
            if any(fragment in path for fragment in _NON_REVIEW_FRAGMENTS):
                continue
            is_review_path = (
                path.startswith("/reviews/")
                or path.endswith("-review")
                or "-review-" in path
                or "/review/" in path
            )
            if not is_review_path:
                continue

            # Reject non-laptop devices (motherboards, monitors, consoles, ...)
            # before spending a request on the review page.
            title = anchor.get_text(" ", strip=True)
            summary = self._card_summary(anchor, title)
            if is_non_laptop_device(title, f"{path} {summary}".strip()):
                continue

            # Target relevance check: require family match when family is known
            if target is not None:
                family = (target.laptop_family or "").lower()
                brand = (target.brand or "").lower()
                haystack = f"{path} {anchor.get_text(' ', strip=True).lower()}"
                if family:
                    family_words = [
                        w for w in family.split()
                        if len(w) >= 3 and w not in {"laptop", "gaming", "series", "notebook"}
                    ]
                    if family_words and not any(w in haystack for w in family_words):
                        continue
                elif brand and brand not in haystack:
                    continue

            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append(absolute)

        return urls

    @staticmethod
    def _card_summary(anchor: Any, title: str) -> str:
        """Return the surrounding card text that follows the link title."""
        container = anchor.find_parent(["article", "li", "div"])
        if container is None:
            return ""
        text = container.get_text(" ", strip=True)
        if title and text.startswith(title):
            return text[len(title) :].strip()
        return text if text != title else ""

    # ── Review page parsing ─────────────────────────────────────────────────

    def _parse_review(self, html: str, review_url: str) -> EditorialReview:
        from bs4 import BeautifulSoup  # noqa: PLC0415 - optional at import time

        soup = BeautifulSoup(html, "html.parser")
        return EditorialReview(
            source=self.platform_name,
            review_url=review_url,
            rating=self._extract_rating(soup),
            pros=self._extract_list(soup, (".pretty-verdict__pros", ".reasons-to-buy", ".pretty-bullets")),
            cons=self._extract_list(soup, (".pretty-verdict__cons", ".reasons-to-avoid")),
            verdict=self._extract_verdict(soup),
        )

    @staticmethod
    def _extract_list(soup: Any, selectors: tuple[str, ...]) -> list[str]:
        items: list[str] = []
        for selector in selectors:
            for container in soup.select(selector):
                for item in container.select("li"):
                    text = item.get_text(" ", strip=True)
                    text = re.sub(r"^[\+\-\s]+", "", text).strip()
                    if text and text not in items:
                        items.append(text)
            if items:
                break
        return items

    @staticmethod
    def _extract_verdict(soup: Any) -> str:
        verdict = soup.select_one(".pretty-verdict__verdict, .verdict")
        if verdict is None:
            return ""
        paragraphs = verdict.select("p")
        if paragraphs:
            return " ".join(p.get_text(" ", strip=True) for p in paragraphs).strip()
        return verdict.get_text(" ", strip=True)

    @staticmethod
    def _extract_rating(soup: Any) -> float | None:
        for selector in (
            '[itemprop="ratingValue"]',
            "meta[property='og:rating']",
            ".rating",
            ".review-rating",
            ".pretty-verdict__rating",
            '[aria-label*="star"]',
            '[aria-label*="Rating"]',
        ):
            node = soup.select_one(selector)
            if node is None:
                continue
            raw = node.get("content") if hasattr(node, "get") else None
            if not raw and hasattr(node, "get"):
                raw = node.get("aria-label")
            if not raw:
                raw = node.get_text(" ", strip=True)
            rating = _parse_rating_text(str(raw or ""))
            if rating is not None:
                return rating
        return None


def _parse_rating_text(text: str) -> float | None:
    """Parse ``"4.5 out of 5"`` / ``"4.5/5"`` / ``"4.5"`` into a float."""
    if not text:
        return None

    match = _RATING_RE.search(text)
    if match:
        value, scale = float(match.group(1)), float(match.group(2))
        if scale <= 0:
            return None
        return round(value * 5.0 / scale, 2) if scale != 5.0 else value

    match = _NUMERIC_RATING_RE.search(text)
    if match:
        return float(match.group(1))
    return None


__all__ = ["LAPTOPMAG_BASE_URL", "LAPTOPMAG_SEARCH_URL", "LaptopMagPlatformScraper"]
