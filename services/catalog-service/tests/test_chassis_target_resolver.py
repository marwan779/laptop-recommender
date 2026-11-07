"""Unit tests for the pure chassis target resolver and review event contracts.

All resolver tests are pure: no database, no network, no framework fixtures.
"""

from __future__ import annotations

import pytest

from app.domain.reviews import (
    ChassisKeyExtractor,
    ChassisTargetResolver,
    LaptopInputDto,
)
from app.schemas.events import (
    LaptopReviewTarget,
    ScrapeReviewsCommand,
    ScrapeReviewsPayload,
)


def _lenovo_loq(
    laptop_id: str,
    canonical_id: str,
    mpn: str,
    model: str = "83DV01HSED",
    ram_gb: int = 16,
    sku: str = "83DV01HSED",
    url: str = "https://compumarts.com/loq",
) -> LaptopInputDto:
    return LaptopInputDto(
        laptop_id=laptop_id,
        canonical_id=canonical_id,
        title=f"Lenovo LOQ 15IRX9 {model} Gaming Laptop - Core i7-13650HX - {ram_gb}GB RAM",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
        mpn=mpn,
        thumbnail_url=f"https://cdn.example.com/{laptop_id}.jpg",
        retailer_skus=(sku,),
        product_urls=(url,),
    )


def _asus_tuf(laptop_id: str, canonical_id: str, mpn: str) -> LaptopInputDto:
    return LaptopInputDto(
        laptop_id=laptop_id,
        canonical_id=canonical_id,
        title="ASUS TUF Gaming A16 FA608PM-RV169W - Ryzen 9 8940HX - RTX 5060",
        brand="ASUS",
        laptop_family="TUF Gaming",
        laptop_model="FA608PM-RV169W",
        mpn=mpn,
        thumbnail_url="https://cdn.example.com/tuf.jpg",
        retailer_skus=("90NR0MC1-M008A0",),
        product_urls=("https://compumarts.com/tuf-a16",),
    )


# ─── Grouping ───────────────────────────────────────────────────────────────


def test_variants_of_same_chassis_collapse_into_one_target():
    resolver = ChassisTargetResolver()

    targets = resolver.resolve(
        [
            _lenovo_loq("lap-1", "lenovo-loq-15irx9-16gb", "83DV01HSED", ram_gb=16, sku="83DV01HSED"),
            _lenovo_loq("lap-2", "lenovo-loq-15irx9-32gb", "83DV01HTED", ram_gb=32, sku="83DV01HTED"),
            _asus_tuf("lap-3", "asus-tuf-a16-fa608pm", "90NR0MC1-M008A0"),
        ]
    )

    assert len(targets) == 2

    loq = next(t for t in targets if t.brand == "Lenovo")
    tuf = next(t for t in targets if t.brand == "ASUS")

    assert loq.variant_count == 2
    assert set(loq.mpns) == {"83DV01HSED", "83DV01HTED"}
    assert set(loq.skus) == {"83DV01HSED", "83DV01HTED"}
    assert loq.chassis_key.startswith("lenovo:")
    assert "15IRX9" in loq.chassis_key

    assert tuf.variant_count == 1
    assert tuf.mpns == ("90NR0MC1-M008A0",)


def test_grouping_preserves_all_mpns_and_deduplicates_skus():
    resolver = ChassisTargetResolver()

    shared_sku = "83DV01HSED"
    targets = resolver.resolve(
        [
            _lenovo_loq("lap-1", "loq-a", "MPN-AAA", sku=shared_sku, url="https://store-a.com/loq"),
            _lenovo_loq("lap-2", "loq-b", "MPN-BBB", sku=shared_sku, url="https://store-b.com/loq"),
            _lenovo_loq("lap-3", "loq-c", "MPN-CCC", sku="83DV01HXED", url="https://store-a.com/loq"),
        ]
    )

    assert len(targets) == 1
    target = targets[0]

    assert target.variant_count == 3
    assert target.mpns == ("MPN-AAA", "MPN-BBB", "MPN-CCC")
    # Shared SKU appears once, extra SKU is appended.
    assert target.skus == (shared_sku, "83DV01HXED")
    # Duplicate product URL collapses, distinct URLs are kept.
    assert target.product_urls == ("https://store-a.com/loq", "https://store-b.com/loq")


def test_representative_identity_comes_from_first_variant():
    resolver = ChassisTargetResolver()

    targets = resolver.resolve(
        [
            _lenovo_loq("lap-first", "canonical-first", "MPN-FIRST"),
            _lenovo_loq("lap-second", "canonical-second", "MPN-SECOND"),
        ]
    )

    assert len(targets) == 1
    target = targets[0]
    assert target.laptop_id == "lap-first"
    assert target.canonical_id == "canonical-first"
    assert target.mpn == "MPN-FIRST"
    assert target.manufacturer_part_number == "MPN-FIRST"
    assert target.thumbnail_url == "https://cdn.example.com/lap-first.jpg"


def test_distinct_chassis_codes_do_not_collapse():
    resolver = ChassisTargetResolver()

    targets = resolver.resolve(
        [
            _lenovo_loq("lap-1", "loq-15irx9", "MPN-1", model="83DV01HSED"),
            LaptopInputDto(
                laptop_id="lap-2",
                canonical_id="loq-15irx10",
                title="Lenovo LOQ 15IRX10 83JE00XEED Gaming Laptop",
                brand="Lenovo",
                laptop_family="LOQ",
                laptop_model="LOQ 15IRX10",
                mpn="MPN-2",
            ),
        ]
    )

    assert len(targets) == 2


# ─── Chassis key extraction ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("model", "title", "expected_code"),
    [
        ("LOQ 15IRX9", None, "15IRX9"),
        (None, "Lenovo Legion Pro 5 16IAX10H 83F500FBIN", "16IAX10H"),
        ("FA608PM-RV169W", None, "FA608PM"),
        ("X1605VA-OACH007W", None, "X1605VA"),
        (None, "HP Victus 15-fa2352TX Gaming Laptop", "15-FA2352TX"),
        (None, "Acer Nitro V ANV15-52-78UM", "ANV15-52"),
        (None, "Lenovo IdeaPad Slim 3 15IRH10 (83K100QNED)", "15IRH10"),
    ],
)
def test_extract_sub_model_from_identity_fields(model, title, expected_code):
    dto = LaptopInputDto(
        laptop_id="lap",
        canonical_id="canonical",
        title=title,
        brand="Lenovo",
        laptop_family="Family",
        laptop_model=model,
    )

    assert ChassisKeyExtractor.extract_sub_model(dto) == expected_code


def test_chassis_key_shape_is_brand_family_sub_model():
    dto = _lenovo_loq("lap", "canonical", "MPN")

    key = ChassisKeyExtractor.extract(dto)

    assert key == "lenovo:loq:15IRX9"


def test_chassis_key_falls_back_to_brand_and_family_without_code():
    dto = LaptopInputDto(
        laptop_id="lap",
        canonical_id="canonical",
        title="Lenovo Yoga 7 2-in-1 Laptop",
        brand="Lenovo",
        laptop_family="Yoga",
        laptop_model="Yoga 7",
    )

    assert ChassisKeyExtractor.extract(dto) == "lenovo:yoga"


# ─── Schema contract ────────────────────────────────────────────────────────


def test_review_target_has_no_search_queries_attribute():
    assert "search_queries" not in LaptopReviewTarget.model_fields

    target = LaptopReviewTarget(laptop_id="lap-1", canonical_id="canonical-1")
    assert not hasattr(target, "search_queries")


def test_review_target_drops_search_queries_kwarg():
    """Pydantic ignores unknown extras, so a legacy caller cannot reintroduce the field."""
    target = LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="canonical-1",
        search_queries=["Lenovo LOQ review"],
    )

    assert not hasattr(target, "search_queries")
    assert "search_queries" not in target.model_dump()


def test_payload_accepts_more_than_fifteen_targets():
    targets = [LaptopReviewTarget(laptop_id=f"lap-{i}", canonical_id=f"canonical-{i}") for i in range(100)]

    payload = ScrapeReviewsPayload(job_id="reviews_batch_abc", targets=targets)

    assert len(payload.targets) == 100


def test_payload_accepts_empty_target_list():
    payload = ScrapeReviewsPayload(job_id="job-empty", targets=[])

    assert payload.targets == []


def test_review_command_round_trip_keeps_aggregated_identity():
    command = ScrapeReviewsCommand(
        payload=ScrapeReviewsPayload(
            job_id="reviews_batch_abc",
            targets=[
                LaptopReviewTarget(
                    laptop_id="lap-1",
                    canonical_id="canonical-1",
                    brand="Lenovo",
                    laptop_family="LOQ",
                    laptop_model="LOQ 15IRX9",
                    mpn="83DV01HSED",
                    manufacturer_part_number="83DV01HSED",
                    retailer_sku="83DV01HSED",
                    skus=["83DV01HSED", "83DV01HTED"],
                    mpns=["83DV01HSED", "83DV01HTED"],
                    product_urls=["https://compumarts.com/loq"],
                    thumbnail_url="https://cdn.example.com/loq.jpg",
                )
            ],
        )
    )

    restored = ScrapeReviewsCommand.model_validate(command.model_dump())

    target = restored.payload.targets[0]
    assert restored.payload.job_id == "reviews_batch_abc"
    assert target.skus == ["83DV01HSED", "83DV01HTED"]
    assert target.mpns == ["83DV01HSED", "83DV01HTED"]
    assert target.product_urls == ["https://compumarts.com/loq"]
    assert not hasattr(target, "search_queries")


# ─── Empty input ────────────────────────────────────────────────────────────


def test_empty_input_returns_empty_list():
    assert ChassisTargetResolver().resolve([]) == []


def test_none_like_input_returns_empty_list():
    assert ChassisTargetResolver().resolve(()) == []
