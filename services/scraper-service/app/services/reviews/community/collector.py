"""Community reviews coordinator.

Runs every registered platform scraper for every target and assembles a
``CommunitiesData`` per chassis. Platform scrapers are injected, so adding a new
source (Facebook, forums, ...) requires only registering another strategy here —
no orchestrator or contract changes.

Pattern B: returns a pure ``chassis_key -> CommunitiesData`` mapping and performs
no file or object-storage I/O.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.reviews.community_queries import CommunityQueryBuilder
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import CommunitiesData, FacebookPost, RedditPost
from app.services.reviews.chassis_key import build_chassis_key
from app.services.reviews.community.contracts import ICommunityPlatformScraper
from app.services.reviews.community.reddit import RedditPlatformScraper
from app.services.reviews.contracts import ICommunitiesReviewsCollector

logger = logging.getLogger("scraper.services.reviews.community.collector")


class CommunitiesReviewsCollector(ICommunitiesReviewsCollector):
    """Coordinate community platform scrapers and build per-chassis review data."""

    def __init__(
        self,
        query_builder: CommunityQueryBuilder | None = None,
        scrapers: list[ICommunityPlatformScraper] | None = None,
    ) -> None:
        self.query_builder = query_builder or CommunityQueryBuilder()
        self.scrapers = scrapers if scrapers is not None else [RedditPlatformScraper()]
        self._reddit_scrapers = [scraper for scraper in self.scrapers if scraper.platform_name == "reddit"]

    async def collect_for_targets(
        self,
        targets: list[LaptopReviewTarget],
    ) -> dict[str, CommunitiesData]:
        """Return ``chassis_key -> CommunitiesData`` for every target."""
        results: dict[str, CommunitiesData] = {}

        for target in targets:
            chassis_key = build_chassis_key(target)
            try:
                results[chassis_key] = await self._collect_for_target(target)
            except Exception as exc:  # noqa: BLE001 - one target must not abort the batch
                logger.warning(
                    "Community collection failed for chassis '%s': %s",
                    chassis_key,
                    exc,
                )
                results[chassis_key] = CommunitiesData()

        return results

    async def _collect_for_target(self, target: LaptopReviewTarget) -> CommunitiesData:
        """Query every registered platform and merge results into one model."""
        queries = self.query_builder.build_queries(target)

        reddit_posts: list[RedditPost] = []
        facebook_posts: list[FacebookPost] = []

        for scraper in self.scrapers:
            posts = await self._run_scraper(scraper, target, queries)
            if scraper.platform_name == "reddit":
                reddit_posts.extend(post for post in posts if isinstance(post, RedditPost))
            elif scraper.platform_name == "facebook":
                facebook_posts.extend(post for post in posts if isinstance(post, FacebookPost))

        # Deduplicate posts if multiple Reddit strategies are registered.
        reddit_posts = self._dedupe_posts(reddit_posts)

        return CommunitiesData(reddit=reddit_posts, facebook=facebook_posts)

    async def _run_scraper(
        self,
        scraper: ICommunityPlatformScraper,
        target: LaptopReviewTarget,
        queries: list[str],
    ) -> list[Any]:
        """Execute one scraper, isolating its failures."""
        try:
            return await scraper.scrape_for_target(target, queries)
        except Exception as exc:  # noqa: BLE001 - platform failures are expected
            logger.warning(
                "Platform '%s' failed for '%s': %s",
                scraper.platform_name,
                target.canonical_id,
                exc,
            )
            return []

    @staticmethod
    def _dedupe_posts(posts: list[RedditPost]) -> list[RedditPost]:
        """Deduplicate by post id, keeping the first (highest-ranked) occurrence."""
        seen: set[str] = set()
        unique: list[RedditPost] = []
        for post in posts:
            if post.post_id in seen:
                continue
            seen.add(post.post_id)
            unique.append(post)
        return unique


__all__ = ["CommunitiesReviewsCollector"]
