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

from app.domain.reviews.community_queries import CommunityQueryBuilder, clean_sub_model
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import CommunityPost
from app.services.reviews.community.contracts import ICommunityPlatformScraper
from app.services.reviews.community.filters import code_tokens, is_deal_listing, is_substantive
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
                    str(topic.get("id")): topic
                    for topic in payload.get("topics") or []
                    if isinstance(topic, dict)
                }
                tokens = self._hardware_tokens(laptop_target)

                results: list[CommunityPost] = []
                seen: set[str] = set()
                for post in payload.get("posts") or []:
                    if not isinstance(post, dict):
                        continue
                    mapped = self._to_community_post(post, topics)
                    if mapped is None or mapped.post_id in seen:
                        continue
                    if not self._passes_gate(mapped, tokens):
                        continue
                    seen.add(mapped.post_id)
                    results.append(mapped)
                    if len(results) >= self.max_results:
                        break

                return results
        except Exception as exc:  # noqa: BLE001 - fail open for every failure mode
            logger.warning("Level1Techs scrape failed for '%s': %s", laptop_target.canonical_id, exc)
            return []

    # ── Relevance gate ─────────────────────────────────────────────────────

    def _passes_gate(self, post: CommunityPost, hardware_tokens: set[str]) -> bool:
        haystack = f"{post.post_title} {post.post_body}".upper()

        # L1: require a chassis/hardware code, unless the target has none.
        if hardware_tokens and not any(token in haystack for token in hardware_tokens):
            return False

        # L2: reject deal/sale threads.
        if is_deal_listing(haystack):
            return False

        # L3: require substantive discussion content.
        return is_substantive(post.post_body, self.min_body_length)

    @staticmethod
    def _hardware_tokens(target: LaptopReviewTarget) -> set[str]:
        """Collect the codes a relevant post should mention."""
        tokens = code_tokens(
            [
                target.laptop_model or "",
                *(target.skus or []),
                target.mpn or "",
                target.manufacturer_part_number or "",
            ]
        )
        sub_model = clean_sub_model(target)
        if sub_model:
            tokens.add(sub_model.upper())
        brand = (target.brand or "").upper()
        family = (target.laptop_family or "").upper()
        return {token for token in tokens if token and token not in {brand, family}}

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
