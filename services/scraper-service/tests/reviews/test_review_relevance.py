"""Fast pure-domain unit tests for Fix 2 relevance, accessory/device veto, and target consolidation."""

from __future__ import annotations

from app.domain.reviews.queries import YouTubeQueryBuilder
from app.domain.reviews.relevance import (
    consolidate_targets_by_chassis,
    contains_word_boundary,
    is_non_laptop_device_text,
    matches_target_text,
)
from app.domain.reviews.vocabulary import normalize_lookup
from app.schemas.events import LaptopReviewTarget


def _target(
    brand: str = "ASUS",
    family: str = "TUF Gaming",
    model: str = "FA608PM-RV169W",
    screen_size: float | None = 16.0,
    mpn: str | None = None,
    chassis_key: str | None = None,
) -> LaptopReviewTarget:
    return LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="canon-1",
        chassis_key=chassis_key,
        brand=brand,
        laptop_family=family,
        laptop_model=model,
        screen_size=screen_size,
        mpn=mpn,
    )


def test_word_boundary_prevents_substring_false_positives():
    tuf_target = _target(brand="ASUS", family="TUF", model="A15 FA506")
    assert contains_word_boundary(normalize_lookup("Lots of STUFF to cover"), "tuf") is False
    assert matches_target_text(tuf_target, "ASUS laptops and cool STUFF to consider") is False
    assert matches_target_text(tuf_target, "ASUS TUF Gaming A15 Review") is True

    pro_target = _target(brand="ASUS", family="VivoBook Pro", model="VivoBook Pro 15")
    assert matches_target_text(pro_target, "ASUS laptop battery PROBLEM solved") is False


def test_brand_and_screen_size_consistency_enforced():
    victus_15 = _target(brand="HP", family="Victus", model="Victus 15", screen_size=15.6)

    # Matching brand + family + size
    assert matches_target_text(victus_15, "HP Victus 15 Gaming Laptop Review") is True
    # Owned sub-brand implies HP cleanly
    assert matches_target_text(victus_15, "Victus 15 thermal test & verdict") is True
    # Conflicting explicit size class in review title must be rejected
    assert matches_target_text(victus_15, "HP Victus 16 Review: Bigger and Faster") is False
    # Different brand must fail
    assert matches_target_text(victus_15, "Acer Nitro V 15 Review") is False


def test_arabic_brand_and_family_aliases_match():
    loq = _target(brand="Lenovo", family="LOQ", model="LOQ 15IRX9", screen_size=15.6)
    assert matches_target_text(loq, "مراجعة لابتوب لينوفو LOQ 15IRX9 للألعاب") is True

    victus = _target(brand="HP", family="Victus", model="Victus 15", screen_size=15.6)
    assert matches_target_text(victus, "تجربة فيكتوس 15 من اتش بي") is True


def test_roundup_titles_rejected_without_exact_code():
    tuf = _target(brand="ASUS", family="TUF Gaming", model="FA608PM")
    assert matches_target_text(tuf, "10 Best Gaming Laptops of 2026", reject_roundups=True) is False
    assert matches_target_text(tuf, "ASUS TUF Gaming A16 FA608PM Review", reject_roundups=True) is True


def test_accessory_and_peripheral_vetoes_do_not_block_real_laptop_reviews():
    # Standalone accessories & peripherals must be rejected
    assert is_non_laptop_device_text("ASUS ROG Backpack Review") is True
    assert is_non_laptop_device_text("Best Laptop Cooling Pad for Lenovo Legion") is True
    assert is_non_laptop_device_text("HP Universal Docking Station Review") is True
    assert is_non_laptop_device_text("ASUS ROG Azoth Gaming Keyboard Review") is True
    assert is_non_laptop_device_text("شاحن لابتوب أصلي 240 واط") is True

    # Real laptop review mentioning keyboard & charger in its body/subtitle must pass
    assert (
        is_non_laptop_device_text(
            "ASUS TUF Gaming A16 FA608PM Review",
            "Comes with a 240W charger, comfortable backlit keyboard, and bright 16-inch display.",
        )
        is False
    )


def test_youtube_query_builder_disambiguates_non_sku_targets():
    builder = YouTubeQueryBuilder()
    sparse = _target(brand="ASUS", family="ROG Strix", model="ROG Strix", screen_size=16.0)
    queries = builder.build_queries(sparse)

    assert queries[0] == "ASUS ROG Strix 16 laptop review"
    assert queries[1] == "مراجعة لابتوب ASUS ROG Strix 16"


def test_consolidate_targets_by_chassis_merges_collisions_and_honors_explicit_key():
    t1 = LaptopReviewTarget(
        laptop_id="id-1",
        canonical_id="canon-1",
        chassis_key="hp:victus:15-FA",
        brand="HP",
        laptop_family="Victus",
        laptop_model="15-FA2317TX",
        mpn="MPN-1",
        skus=["SKU-1"],
        mpns=["MPN-1"],
        product_urls=["https://store.example/1"],
        matched_laptop_ids=["id-1"],
        matched_canonical_ids=["canon-1"],
    )
    t2 = LaptopReviewTarget(
        laptop_id="id-2",
        canonical_id="canon-2",
        chassis_key="hp:victus:15-FA",
        brand="HP",
        laptop_family="Victus",
        laptop_model="Victus 15",
        mpn="MPN-2",
        skus=["SKU-1", "SKU-2"],
        mpns=["MPN-2"],
        product_urls=["https://store.example/2"],
        screen_size=15.6,
        matched_laptop_ids=["id-2"],
        matched_canonical_ids=["canon-2"],
    )

    merged = consolidate_targets_by_chassis([t1, t2])
    assert len(merged) == 1
    item = merged[0]
    assert item.chassis_key == "hp:victus:15-FA"
    assert item.matched_laptop_ids == ["id-1", "id-2"]
    assert item.matched_canonical_ids == ["canon-1", "canon-2"]
    assert item.skus == ["SKU-1", "SKU-2"]
    assert item.mpns == ["MPN-1", "MPN-2"]
    assert item.product_urls == ["https://store.example/1", "https://store.example/2"]
    assert item.screen_size == 15.6


def test_community_relevance_rejects_sibling_series_conflicting_codes_and_body_only_hits():
    scar_18 = _target(
        brand="ASUS",
        family="Rog Strix Scar",
        model="ASUS ROG Strix SCAR 18 G835LX-AI464W",
        screen_size=18.0,
    )
    assert (
        matches_target_text(
            scar_18,
            "Asus ROG Strix SCAR 18 (2026) REVIEW - The FASTEST Gaming Laptop",
            require_brand=True,
        )
        is True
    )
    assert (
        matches_target_text(
            scar_18,
            "ASUS ROG Strix G18 G815 review",
            url="https://www.laptopmag.com/laptops/gaming-laptops-pcs/asus-rog-strix-g18-g815-review",
            require_headline_match=True,
        )
        is False
    )
    assert (
        matches_target_text(
            scar_18,
            "ASUS ROG Strix Scar 16 won't show logo and reboots",
            require_headline_match=True,
        )
        is False
    )
    assert (
        matches_target_text(
            scar_18,
            "مراجعة ASUS ROG Strix SCAR III G731GV",
            require_headline_match=True,
        )
        is False
    )

    helios = _target(
        brand="Acer",
        family="Predator Helios Neo",
        model="Predator Helios Neo 16",
        screen_size=16.0,
    )
    assert matches_target_text(helios, "Acer Helios Neo 16 (2024) Review") is True
    assert (
        matches_target_text(
            helios,
            "Acer Predator Triton Neo 16 review",
            require_headline_match=True,
        )
        is False
    )

    vivobook_14 = _target(
        brand="ASUS",
        family="Vivobook",
        model="TP3407SA-SG157W",
        screen_size=14.0,
    )
    assert (
        matches_target_text(
            vivobook_14,
            "ASUS Vivobook 14 Flip (TP3407SA) Review",
            require_headline_match=True,
        )
        is True
    )
    assert (
        matches_target_text(
            vivobook_14,
            "ASUS Vivobook 16 Flip TP3607 review",
            url="https://www.laptopmag.com/laptops/2-in-1-laptops/asus-vivobook-16-flip-tp3607-review",
            require_headline_match=True,
        )
        is False
    )

    omnibook = _target(
        brand="HP",
        family="omnibook",
        model="OmniBook 5 Flip 14-FP0023DX",
        screen_size=14.0,
    )
    assert (
        matches_target_text(
            omnibook,
            "HP ZBook Ultra 14 G1a review",
            body="Compare with HP OmniBook 5 Flip in our sidebar.",
            require_headline_match=True,
        )
        is False
    )

    vector = _target(
        brand="MSI",
        family="Vector",
        model="Vector 16 HX AI A2XWHG-676EG",
        screen_size=16.0,
    )
    assert (
        matches_target_text(
            vector,
            "No irq handler for vector",
            body="Linux kernel vector interrupt debugging thread.",
            require_headline_match=True,
        )
        is False
    )

    strix_sparse = _target(
        brand="ASUS",
        family="Rog Strix",
        model="ROG Strix",
        screen_size=16.0,
    )
    assert (
        matches_target_text(
            strix_sparse,
            "Asus ROG Flow Z13 (2025) review",
            url="https://www.laptopmag.com/laptops/gaming-laptops-pcs/asus-rog-flow-z13-2025-review",
            require_headline_match=True,
        )
        is False
    )
