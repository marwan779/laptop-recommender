"""Schema tests for the batched review scraping command."""

import pytest
from pydantic import ValidationError

from app.schemas.events import (
    REVIEWS_BATCH_MAX_TARGETS,
    LaptopReviewTarget,
    ScrapeReviewsCommand,
    ScrapeReviewsPayload,
)


def _target(index: int) -> LaptopReviewTarget:
    return LaptopReviewTarget(
        laptop_id=f"lap-{index}",
        canonical_id=f"canonical-{index}",
        title="ASUS Vivobook 16 X1605VA-OACH007W Review",
        brand="ASUS",
        laptop_family="Vivobook",
        laptop_model="Vivobook 16",
        mpn="90NB10N2M02TC0",
        manufacturer_part_number="90NB10N2-M02TC0",
        retailer_sku="90NB10N2-M02TC0",
        skus=["X1605VA-OACH007W", "X1605VA"],
        mpns=["90NB10N2-M02TC0"],
        product_urls=["https://www.compumarts.com/products/asus-vivobook-16"],
        thumbnail_url="https://www.compumarts.com/cdn/shop/files/ASUS-Vivobook-16.jpg",
        search_queries=["ASUS Vivobook 16 review"],
    )


def test_review_target_accepts_identity_and_batch_fields():
    target = _target(1)

    assert target.laptop_id == "lap-1"
    assert target.canonical_id == "canonical-1"
    assert target.laptop_model == "Vivobook 16"
    assert target.skus == ["X1605VA-OACH007W", "X1605VA"]
    assert target.mpns == ["90NB10N2-M02TC0"]
    assert target.product_urls == ["https://www.compumarts.com/products/asus-vivobook-16"]
    assert target.search_queries == ["ASUS Vivobook 16 review"]


def test_batch_accepts_up_to_15_targets():
    payload = ScrapeReviewsPayload(
        job_id="job-123",
        targets=[_target(index) for index in range(REVIEWS_BATCH_MAX_TARGETS)],
    )

    assert len(payload.targets) == 15


def test_batch_rejects_more_than_15_targets():
    with pytest.raises(ValidationError):
        ScrapeReviewsPayload(
            job_id="job-123",
            targets=[_target(index) for index in range(REVIEWS_BATCH_MAX_TARGETS + 1)],
        )


def test_empty_batch_is_still_allowed_for_backward_compatibility():
    payload = ScrapeReviewsPayload(job_id="job-empty", targets=[])

    assert payload.targets == []


def test_review_command_serialization_round_trip_keeps_identity_fields():
    command = ScrapeReviewsCommand(
        payload=ScrapeReviewsPayload(job_id="job-round-trip", targets=[_target(1)])
    )

    restored = ScrapeReviewsCommand.model_validate(command.model_dump())

    assert restored.payload.targets[0].laptop_id == "lap-1"
    assert restored.payload.targets[0].skus == ["X1605VA-OACH007W", "X1605VA"]
    assert restored.payload.targets[0].mpns == ["90NB10N2-M02TC0"]
    assert restored.payload.targets[0].laptop_model == "Vivobook 16"
