"""Strategy contract for community platform scrapers.

Each platform (Reddit, Facebook, forums, ...) implements this narrow interface
so new sources can be registered without modifying the coordinator
(Open/Closed Principle). A scraper receives one target plus the pre-built
aspect queries and returns platform-native post models.

Scrapers must be fail-open: a network error should yield an empty list rather
than aborting the whole collection run.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.events import LaptopReviewTarget


class ICommunityPlatformScraper(ABC):
    """Contract for scraping one community platform for a single laptop target."""

    #: Stable identifier for the platform (e.g. ``"reddit"``).
    platform_name: str

    @abstractmethod
    async def scrape_for_target(
        self,
        laptop_target: LaptopReviewTarget,
        queries: list[str],
    ) -> list[Any]:
        """Return platform-native post models relevant to the target.

        Args:
            laptop_target: The chassis target being researched.
            queries: Pre-built aspect queries to run on this platform.

        Returns:
            A list of platform post objects (e.g. ``RedditPost``). Must never
            raise for ordinary network/site failures.
        """
        ...


__all__ = ["ICommunityPlatformScraper"]
