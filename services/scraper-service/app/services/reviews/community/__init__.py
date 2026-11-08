"""Community review collection: platform strategies and the coordinator.

Adding a platform means implementing ``ICommunityPlatformScraper`` and passing
an instance to ``CommunitiesReviewsCollector(scrapers=[...])``.
"""

from app.services.reviews.community.arabhardware import ArabhardwarePlatformScraper
from app.services.reviews.community.collector import CommunitiesReviewsCollector
from app.services.reviews.community.contracts import ICommunityPlatformScraper
from app.services.reviews.community.laptopmag import LaptopMagPlatformScraper
from app.services.reviews.community.level1techs import Level1TechsPlatformScraper
from app.services.reviews.community.reddit import (
    DEFAULT_USER_AGENT,
    REDDIT_BASE_URL,
    RedditPlatformScraper,
    SubTargets,
)

__all__ = [
    "DEFAULT_USER_AGENT",
    "REDDIT_BASE_URL",
    "ArabhardwarePlatformScraper",
    "CommunitiesReviewsCollector",
    "ICommunityPlatformScraper",
    "LaptopMagPlatformScraper",
    "Level1TechsPlatformScraper",
    "RedditPlatformScraper",
    "SubTargets",
]
