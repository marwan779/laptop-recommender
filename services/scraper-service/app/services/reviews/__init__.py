"""Application-layer package for review collection use cases."""

from app.services.reviews.collector import ReviewCollectorService, build_s3_key
from app.services.reviews.contracts import (
    ICommunitiesReviewsCollector,
    IYouTubeReviewsCollector,
    StubCommunitiesReviewsCollector,
    StubYouTubeReviewsCollector,
)

__all__ = [
    "ICommunitiesReviewsCollector",
    "IYouTubeReviewsCollector",
    "ReviewCollectorService",
    "StubCommunitiesReviewsCollector",
    "StubYouTubeReviewsCollector",
    "build_s3_key",
]
