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

__all__ = [
    "ChassisKeyExtractor",
    "ChassisTargetResolver",
    "LaptopInputDto",
    "ResolvedReviewTarget",
]
