"""Schema tests for the batched review scraping command."""

import pytest
from pydantic import ValidationError

from app.schemas.events import (
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
        matched_laptop_ids=[f"lap-{index}"],
        matched_canonical_ids=[f"canonical-{index}"],
    )


def test_review_target_accepts_identity_and_batch_fields():
    target = _target(1)

    assert target.laptop_id == "lap-1"
    assert target.canonical_id == "canonical-1"
    assert target.laptop_model == "Vivobook 16"
    assert target.skus == ["X1605VA-OACH007W", "X1605VA"]
    assert target.mpns == ["90NB10N2-M02TC0"]
    assert target.product_urls == ["https://www.compumarts.com/products/asus-vivobook-16"]
    assert target.matched_laptop_ids == ["lap-1"]
    assert target.matched_canonical_ids == ["canonical-1"]
    assert not hasattr(target, "search_queries")


def test_batch_accepts_full_chassis_batch():
    payload = ScrapeReviewsPayload(
        job_id="job-123",
        targets=[_target(index) for index in range(90)],
    )

    assert len(payload.targets) == 90


def test_batch_has_no_upper_target_cap():
    # Previously capped at 15; full chassis batches must pass unchanged.
    payload = ScrapeReviewsPayload(
        job_id="job-123",
        targets=[_target(index) for index in range(150)],
    )

    assert len(payload.targets) == 150


def test_empty_batch_is_still_allowed_for_backward_compatibility():
    payload = ScrapeReviewsPayload(job_id="job-empty", targets=[])

    assert payload.targets == []


def test_review_command_serialization_round_trip_keeps_identity_fields():
    command = ScrapeReviewsCommand(payload=ScrapeReviewsPayload(job_id="job-round-trip", targets=[_target(1)]))

    restored = ScrapeReviewsCommand.model_validate(command.model_dump())

    assert restored.payload.targets[0].laptop_id == "lap-1"
    assert restored.payload.targets[0].skus == ["X1605VA-OACH007W", "X1605VA"]
    assert restored.payload.targets[0].mpns == ["90NB10N2-M02TC0"]
    assert restored.payload.targets[0].laptop_model == "Vivobook 16"
    assert restored.payload.targets[0].matched_laptop_ids == ["lap-1"]
    assert restored.payload.targets[0].matched_canonical_ids == ["canonical-1"]


def test_matched_ids_default_to_empty_lists():
    target = LaptopReviewTarget(laptop_id="lap-1", canonical_id="canonical-1")

    assert target.matched_laptop_ids == []
    assert target.matched_canonical_ids == []
