"""Level1Techs forum scraper (pure Discourse REST JSON).

Flow:
    1. ``GET https://forum.level1techs.com/search.json?q={forum_query}``
    2. Map the JSON ``posts`` array onto ``CommunityPost`` objects.
    3. Apply three relevance layers:
         L1 hardware token match  - the post must mention the chassis code.
         L2 negative deal filter  - discard sale/deal listings.
         L3 content depth         - require a substantive blurb (>= 40 chars).

Fail-open: transport, HTTP, or JSON failures return an empty list.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus

from app.domain.reviews.community_queries import CommunityQueryBuilder
from app.domain.reviews.relevance import matches_target_text
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import CommunityPost
from app.services.reviews.community.contracts import ICommunityPlatformScraper
from app.services.reviews.community.filters import (
    is_deal_listing,
    is_non_laptop_device,
    is_substantive,
)
from app.services.reviews.community.http import DEFAULT_USER_AGENT, HttpClientContext, get_json

logger = logging.getLogger("scraper.services.reviews.community.level1techs")

LEVEL1TECHS_BASE_URL = "https://forum.level1techs.com"
LEVEL1TECHS_SEARCH_URL = f"{LEVEL1TECHS_BASE_URL}/search.json?q={{query}}"


class Level1TechsPlatformScraper(ICommunityPlatformScraper):
    """Scrape the Level1Techs Discourse forum for hardware discussions."""

    platform_name = "level1techs"

    def __init__(
        self,
        http_client: Any | None = None,
        query_builder: CommunityQueryBuilder | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        max_results: int = 10,
        min_body_length: int = 40,
    ) -> None:
        self.http_client = http_client
        self.query_builder = query_builder or CommunityQueryBuilder()
        self.user_agent = user_agent
        self.max_results = max_results
        self.min_body_length = min_body_length

    async def scrape_for_target(
        self,
        laptop_target: LaptopReviewTarget,
        queries: list[str],
    ) -> list[CommunityPost]:
        """Return gated forum posts for one target. Never raises."""
        query = self.query_builder.forum_query(laptop_target)
        if not query:
            return []

        try:
            async with HttpClientContext(self.http_client, self.user_agent) as client:
                url = LEVEL1TECHS_SEARCH_URL.format(query=quote_plus(query))
                payload = await get_json(client, url)
                if not isinstance(payload, dict):
                    return []

                topics = {
                    str(topic.get("id")): topic for topic in payload.get("topics") or [] if isinstance(topic, dict)
                }

                results: list[CommunityPost] = []
                seen: set[str] = set()
                for post in payload.get("posts") or []:
                    if not isinstance(post, dict):
                        continue
                    mapped = self._to_community_post(post, topics)
                    if mapped is None or mapped.post_id in seen:
                        continue
                    if not self._passes_gate(mapped, laptop_target):
                        continue
                    seen.add(mapped.post_id)

                    # Hydrate full un-truncated post body from Discourse post API
                    full_body = await self._fetch_full_post(client, mapped.post_id)
                    if full_body:
                        if is_non_laptop_device(mapped.post_title, full_body) or is_deal_listing(full_body):
                            continue
                        mapped = CommunityPost(
                            platform=mapped.platform,
                            post_id=mapped.post_id,
                            author=mapped.author,
                            post_title=mapped.post_title,
                            post_url=mapped.post_url,
                            post_body=full_body,
                            score=mapped.score,
                            published_at=mapped.published_at,
                            comments=mapped.comments,
                        )

                    results.append(mapped)
                    if len(results) >= self.max_results:
                        break

                return results
        except Exception as exc:  # noqa: BLE001 - fail open for every failure mode
            logger.warning("Level1Techs scrape failed for '%s': %s", laptop_target.canonical_id, exc)
            return []

    @staticmethod
    async def _fetch_full_post(client: Any, post_id: str) -> str | None:
        """Fetch un-truncated post body from Discourse post endpoint."""
        try:
            url = f"{LEVEL1TECHS_BASE_URL}/posts/{post_id}.json"
            data = await get_json(client, url)
            if isinstance(data, dict):
                raw = str(data.get("raw") or "").strip()
                if raw:
                    return raw
                cooked = str(data.get("cooked") or "").strip()
                if cooked:
                    from bs4 import BeautifulSoup

                    return BeautifulSoup(cooked, "html.parser").get_text(" ", strip=True)
        except Exception:  # noqa: BLE001 - fail-open to blurb
            pass
        return None

    # ── Relevance gate ─────────────────────────────────────────────────────

    def _passes_gate(
        self,
        post: CommunityPost,
        target: LaptopReviewTarget,
    ) -> bool:
        haystack = f"{post.post_title} {post.post_body}"

        # L1: strict word-boundary headline/URL + brand + series/code relevance.
        has_domain_match = matches_target_text(
            target,
            post.post_title,
            post.post_body,
            post.post_url,
            require_brand=True,
            require_headline_match=True,
        )
        if not has_domain_match:
            return False

        # L1b: reject non-laptop devices & accessories.
        if is_non_laptop_device(post.post_title, post.post_body):
            return False

        # L2: reject deal/sale threads.
        if is_deal_listing(haystack):
            return False

        # L3: require substantive discussion content.
        return is_substantive(post.post_body, self.min_body_length)

    # ── Mapping ────────────────────────────────────────────────────────────

    @staticmethod
    def _to_community_post(
        post: dict[str, Any],
        topics: dict[str, Any],
    ) -> CommunityPost | None:
        post_id = str(post.get("id") or "").strip()
        if not post_id:
            return None

        topic = topics.get(str(post.get("topic_id"))) or {}
        slug = str(topic.get("slug") or "topic")
        topic_id = str(post.get("topic_id") or topic.get("id") or "")
        post_number = post.get("post_number")
        post_url = (
            f"{LEVEL1TECHS_BASE_URL}/t/{slug}/{topic_id}/{post_number}"
            if topic_id and post_number
            else str(post.get("url") or "")
        )

        body = str(post.get("blurb") or post.get("cooked") or post.get("excerpt") or "").strip()
        score = post.get("score")
        if not isinstance(score, int):
            score = post.get("like_count") if isinstance(post.get("like_count"), int) else None

        return CommunityPost(
            platform="level1techs",
            post_id=post_id,
            author=post.get("username") or post.get("author"),
            post_title=str(topic.get("title") or post.get("title") or ""),
            post_url=post_url,
            post_body=body,
            score=score,
            published_at=post.get("created_at"),
        )


__all__ = ["LEVEL1TECHS_BASE_URL", "LEVEL1TECHS_SEARCH_URL", "Level1TechsPlatformScraper"]
