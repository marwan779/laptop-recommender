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
    # Every grouped variant ID is carried on the resolved target.
    assert loq.matched_laptop_ids == ("lap-1", "lap-2")
    assert loq.matched_canonical_ids == ("lenovo-loq-15irx9-16gb", "lenovo-loq-15irx9-32gb")
    assert loq.laptop_id == loq.matched_laptop_ids[0]

    assert tuf.variant_count == 1
    assert tuf.mpns == ("90NR0MC1-M008A0",)
    assert tuf.matched_laptop_ids == ("lap-3",)
    assert tuf.matched_canonical_ids == ("asus-tuf-a16-fa608pm",)


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
    # Matched IDs preserve every variant, in input order, without deduplication loss.
    assert target.matched_laptop_ids == ("lap-1", "lap-2", "lap-3")
    assert target.matched_canonical_ids == ("loq-a", "loq-b", "loq-c")


def test_every_variant_id_is_matched_exactly_once():
    resolver = ChassisTargetResolver()

    targets = resolver.resolve(
        [
            _lenovo_loq("lap-1", "loq-a", "MPN-AAA"),
            _lenovo_loq("lap-2", "loq-b", "MPN-BBB"),
            _asus_tuf("lap-3", "tuf-a", "90NR0MC1-M008A0"),
        ]
    )

    all_laptop_ids = [lid for target in targets for lid in target.matched_laptop_ids]
    all_canonical_ids = [cid for target in targets for cid in target.matched_canonical_ids]

    assert sorted(all_laptop_ids) == ["lap-1", "lap-2", "lap-3"]
    assert sorted(all_canonical_ids) == ["loq-a", "loq-b", "tuf-a"]
    assert all(len(target.matched_laptop_ids) == target.variant_count for target in targets)
    assert all(len(target.matched_canonical_ids) == target.variant_count for target in targets)


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
        (None, "HP Victus 15-fa2352TX Gaming Laptop", "15-FA"),
        (None, "Acer Nitro V ANV15-52-78UM", "ANV15-52"),
        (None, "Lenovo IdeaPad Slim 3 15IRH10 (83K100QNED)", "15IRH10"),
        (None, "MSI Prestige 13 AI Evo A1MG", "A1MG"),
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


# ─── Screen size aggregation ────────────────────────────────────────────────


def test_resolver_uses_modal_screen_size_across_variants():
    resolver = ChassisTargetResolver()

    def variant(laptop_id: str, screen_size: float | None) -> LaptopInputDto:
        return LaptopInputDto(
            laptop_id=laptop_id,
            canonical_id=f"loq-{laptop_id}",
            brand="Lenovo",
            laptop_family="LOQ",
            laptop_model="LOQ 15IRX9",
            screen_size=screen_size,
        )

    targets = resolver.resolve(
        [
            variant("a", 15.6),
            variant("b", 16.0),
            variant("c", 15.6),
        ]
    )

    assert len(targets) == 1
    assert targets[0].screen_size == 15.6


def test_resolver_falls_back_to_first_non_null_screen_size():
    resolver = ChassisTargetResolver()

    def variant(laptop_id: str, screen_size: float | None) -> LaptopInputDto:
        return LaptopInputDto(
            laptop_id=laptop_id,
            canonical_id=f"loq-{laptop_id}",
            brand="Lenovo",
            laptop_family="LOQ",
            laptop_model="LOQ 15IRX9",
            screen_size=screen_size,
        )

    targets = resolver.resolve([variant("a", None), variant("b", 16.0), variant("c", 15.6)])

    assert len(targets) == 1
    assert targets[0].screen_size == 16.0


def test_resolver_leaves_screen_size_none_without_data():
    targets = ChassisTargetResolver().resolve(
        [LaptopInputDto(laptop_id="a", canonical_id="c", brand="Lenovo", laptop_family="LOQ")]
    )

    assert targets[0].screen_size is None


def test_none_like_input_returns_empty_list():
    assert ChassisTargetResolver().resolve(()) == []


# ─── Realistic physical chassis grouping ─────────────────────────────────────


def test_hp_victus_regional_skus_collapse_to_series_and_separate_amd():
    resolver = ChassisTargetResolver()

    targets = resolver.resolve(
        [
            LaptopInputDto(
                laptop_id="v1",
                canonical_id="hp-victus-15-fa2317tx",
                brand="HP",
                laptop_family="Victus",
                laptop_model="15-FA2317TX",
                mpn="15FA2317TX",
                screen_size=15.6,
            ),
            LaptopInputDto(
                laptop_id="v2",
                canonical_id="hp-victus-15-fa2082wm",
                brand="HP",
                laptop_family="Victus",
                laptop_model="HP Victus 15-fa2082wm",
                mpn="B5EQ3UA",
                screen_size=15.6,
            ),
            LaptopInputDto(
                laptop_id="v3",
                canonical_id="hp-victus-15-fa1043ne",
                brand="HP",
                laptop_family="Victus",
                laptop_model="Victus 15",
                mpn="15FA1043NE",
                screen_size=15.6,
            ),
            LaptopInputDto(
                laptop_id="v4",
                canonical_id="hp-victus-15-fb3093dx",
                brand="HP",
                laptop_family="Victus",
                laptop_model="15-fb3093dx",
                mpn="FB3093DX",
                screen_size=15.6,
            ),
        ]
    )

    assert len(targets) == 2
    assert {t.chassis_key for t in targets} == {"hp:victus:15-FA", "hp:victus:15-FB"}
    fa_group = next(t for t in targets if t.chassis_key == "hp:victus:15-FA")
    assert fa_group.matched_laptop_ids == ("v1", "v2", "v3")


def test_screen_size_and_tier_keep_distinct_chassis_apart_without_codes():
    resolver = ChassisTargetResolver()

    targets = resolver.resolve(
        [
            LaptopInputDto(
                laptop_id="viv15",
                canonical_id="asus-vivobook-15",
                brand="ASUS",
                laptop_family="Vivobook",
                laptop_model="Vivobook 15",
                screen_size=15.6,
            ),
            LaptopInputDto(
                laptop_id="viv16",
                canonical_id="asus-vivobook-16",
                brand="ASUS",
                laptop_family="Vivobook",
                laptop_model="Vivobook 16",
                screen_size=16.0,
            ),
            LaptopInputDto(
                laptop_id="ip-2in1",
                canonical_id="lenovo-ideapad-5-2in1",
                brand="Lenovo",
                laptop_family="IdeaPad",
                laptop_model="IdeaPad 5 2-in-1",
                screen_size=14.0,
            ),
            LaptopInputDto(
                laptop_id="ip-gaming",
                canonical_id="lenovo-ideapad-gaming-3",
                brand="Lenovo",
                laptop_family="IdeaPad",
                laptop_model="IdeaPad Gaming 3",
                screen_size=15.6,
            ),
        ]
    )

    assert len(targets) == 4
    keys = {t.chassis_key for t in targets}
    assert len(keys) == 4
    assert "asus:vivobook:15" in keys
    assert "asus:vivobook:16" in keys


def test_loq_essential_and_lenovo_mtm_stay_distinct():
    resolver = ChassisTargetResolver()

    targets = resolver.resolve(
        [
            LaptopInputDto(
                laptop_id="ess",
                canonical_id="loq-ess",
                brand="Lenovo",
                laptop_family="LOQ Essential",
                laptop_model="83S000C2IN",
                mpn="83S000C2IN",
            ),
            LaptopInputDto(
                laptop_id="loq-1",
                canonical_id="loq-1",
                brand="Lenovo",
                laptop_family="LOQ",
                laptop_model="83DV01HSED",
                mpn="83DV01HSED",
            ),
            LaptopInputDto(
                laptop_id="loq-2",
                canonical_id="loq-2",
                brand="Lenovo",
                laptop_family="LOQ",
                laptop_model="83DV012HED",
                mpn="83DV012HED",
            ),
            LaptopInputDto(
                laptop_id="loq-3",
                canonical_id="loq-3",
                brand="Lenovo",
                laptop_family="LOQ",
                laptop_model="83JC0057PS",
                mpn="83JC0057PS",
            ),
        ]
    )

    keys = {t.chassis_key: t for t in targets}
    assert set(keys) == {"lenovo:loq-essential:83S0", "lenovo:loq:83DV", "lenovo:loq:83JC"}
    assert keys["lenovo:loq:83DV"].matched_laptop_ids == ("loq-1", "loq-2")


def test_to_review_target_preserves_resolved_chassis_key():
    from app.services.catalog_ingestion_service import CatalogIngestionService

    resolved = ChassisTargetResolver().resolve([_lenovo_loq("lap-1", "loq-15irx9", "83DV01HSED")])[0]
    transport = CatalogIngestionService._to_review_target(resolved)

    assert transport.chassis_key == resolved.chassis_key == "lenovo:loq:15IRX9"


def test_family_inference_recovers_generic_and_polluted_db_families():
    resolver = ChassisTargetResolver()

    targets = resolver.resolve(
        [
            LaptopInputDto(
                laptop_id="hp-omni",
                canonical_id="hp-omnibook-5-flip-14-fp",
                brand="HP",
                laptop_family="HP",
                laptop_model="OmniBook 5 Flip 14-FP0023DX",
                title="HP OmniBook 5 Flip 14-FP0023DX 2 In 1 Laptop",
                screen_size=14.0,
            ),
            LaptopInputDto(
                laptop_id="asus-viv",
                canonical_id="asus-vivobook-16-x1607ca",
                brand="ASUS",
                laptop_family="Notebook",
                laptop_model="Vivobook 16 X1607CA-MB157W",
                title="ASUS Vivobook 16 X1607CA-MB157W Laptop",
                screen_size=16.0,
            ),
            LaptopInputDto(
                laptop_id="len-flex",
                canonical_id="lenovo-flex-5-14iau7",
                brand="Lenovo",
                laptop_family="Lenovo",
                laptop_model="FLEX 5 14IAU7",
                title="Lenovo FLEX 5 14IAU7 82R700L4US 2-IN-1",
                screen_size=14.0,
            ),
            LaptopInputDto(
                laptop_id="asus-cpu",
                canonical_id="asus-zenbook-ux3407qa",
                brand="ASUS",
                laptop_family="Ultra 7",
                laptop_model="UX3407QA",
                title="ASUS Zenbook A14 UX3407QA Core Ultra 7 Laptop",
                screen_size=14.0,
            ),
        ]
    )

    assert {t.chassis_key for t in targets} == {
        "hp:omnibook:14-FP",
        "asus:vivobook:X1607CA",
        "lenovo:flex:14IAU7",
        "asus:zenbook:UX3407QA",
    }
