"""Application-layer package for review collection use cases."""

from app.services.reviews.chassis_key import build_chassis_key
from app.services.reviews.collector import ReviewCollectorService, build_s3_key
from app.services.reviews.community import (
    CommunitiesReviewsCollector,
    ICommunityPlatformScraper,
    RedditPlatformScraper,
    SubTargets,
)
from app.services.reviews.contracts import (
    ICommunitiesReviewsCollector,
    IYouTubeReviewsCollector,
    StubCommunitiesReviewsCollector,
    StubYouTubeReviewsCollector,
)
from app.services.reviews.youtube import (
    YouTubeReviewsCollector,
    YouTubeSearchService,
    YouTubeTranscriptService,
)

__all__ = [
    "CommunitiesReviewsCollector",
    "ICommunitiesReviewsCollector",
    "ICommunityPlatformScraper",
    "IYouTubeReviewsCollector",
    "RedditPlatformScraper",
    "ReviewCollectorService",
    "StubCommunitiesReviewsCollector",
    "StubYouTubeReviewsCollector",
    "SubTargets",
    "YouTubeReviewsCollector",
    "YouTubeSearchService",
    "YouTubeTranscriptService",
    "build_chassis_key",
    "build_s3_key",
]
