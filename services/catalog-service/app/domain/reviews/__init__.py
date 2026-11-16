"""Pure domain package for community review aggregation.

Exposes the chassis resolver that collapses multi-SKU laptop variants into a
single review target per physical chassis.
"""

from app.domain.reviews.chassis import (
    ChassisKeyExtractor,
    ChassisTargetResolver,
    LaptopInputDto,
    ResolvedReviewTarget,
)
from app.domain.reviews.sources import (
    ReviewSourceItem,
    clean_http_url,
    extract_review_sources,
    normalize_review_sources_collection,
    sort_and_deduplicate_sources,
)

__all__ = [
    "ChassisKeyExtractor",
    "ChassisTargetResolver",
    "LaptopInputDto",
    "ResolvedReviewTarget",
    "ReviewSourceItem",
    "clean_http_url",
    "extract_review_sources",
    "normalize_review_sources_collection",
    "sort_and_deduplicate_sources",
]
