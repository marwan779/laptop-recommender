"""Contract tests for the batched review command in catalog-service."""

from app.schemas.events import (
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
    )


def test_catalog_review_batch_accepts_full_chassis_batch():
    payload = ScrapeReviewsPayload(
        job_id="job-123",
        targets=[_target(index) for index in range(70)],
    )

    assert len(payload.targets) == 70
    assert payload.targets[0].skus == ["83DV01HSED"]


def test_catalog_review_batch_has_no_upper_target_cap():
    payload = ScrapeReviewsPayload(
        job_id="job-123",
        targets=[_target(index) for index in range(150)],
    )

    assert len(payload.targets) == 150


def test_catalog_review_target_exposes_no_search_queries():
    assert "search_queries" not in LaptopReviewTarget.model_fields
