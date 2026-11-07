"""Contract tests for the batched review command in catalog-service."""

import pytest
from pydantic import ValidationError

from app.schemas.events import (
    REVIEWS_BATCH_MAX_TARGETS,
    LaptopReviewTarget,
    ScrapeReviewsPayload,
)


def _target(index: int) -> LaptopReviewTarget:
    return LaptopReviewTarget(
        laptop_id=f"lap-{index}",
        canonical_id=f"canonical-{index}",
        title="Lenovo LOQ 15 Review",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15",
        mpn="83DV01HSED",
        manufacturer_part_number="83DV01HSED",
        retailer_sku="83DV01HSED",
        skus=["83DV01HSED"],
        mpns=["83DV01HSED"],
        product_urls=["https://example.com/lenovo-loq-15"],
        thumbnail_url="https://example.com/lenovo-loq-15.jpg",
        search_queries=["Lenovo LOQ 15 review"],
    )


def test_catalog_review_batch_accepts_15_targets():
    payload = ScrapeReviewsPayload(
        job_id="job-123",
        targets=[_target(index) for index in range(REVIEWS_BATCH_MAX_TARGETS)],
    )

    assert len(payload.targets) == 15
    assert payload.targets[0].skus == ["83DV01HSED"]


def test_catalog_review_batch_rejects_16_targets():
    with pytest.raises(ValidationError):
        ScrapeReviewsPayload(
            job_id="job-123",
            targets=[_target(index) for index in range(REVIEWS_BATCH_MAX_TARGETS + 1)],
        )
