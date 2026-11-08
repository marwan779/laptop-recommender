"""Unit tests for pure community review query building."""

from app.domain.reviews.community_queries import ASPECT_QUERY_TEMPLATES, CommunityQueryBuilder
from app.schemas.events import LaptopReviewTarget


def test_build_queries_produces_four_aspects():
    target = LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
    )
    builder = CommunityQueryBuilder()
    queries = builder.build_queries(target)

    assert len(queries) == 4
    assert queries[0] == "Lenovo LOQ 15IRX9 (thermals OR cooling OR overheating OR temperatures)"
    assert queries[1] == "Lenovo LOQ 15IRX9 (hinge OR build quality OR flex OR durability)"
    assert queries[2] == "Lenovo LOQ 15IRX9 (fan noise OR loud fans OR battery life OR battery drain)"
    assert queries[3] == "Lenovo LOQ 15IRX9 review"


def test_build_queries_deduplicates_repeated_family_prefix():
    target = LaptopReviewTarget(
        laptop_id="lap-2",
        canonical_id="hp-victus-15-fa2352tx",
        brand="HP",
        laptop_family="Victus",
        laptop_model="HP Victus 15-fa2352TX",
    )
    queries = CommunityQueryBuilder().build_queries(target)

    assert len(queries) == len(ASPECT_QUERY_TEMPLATES)
    for q in queries:
        assert "HP HP" not in q
        assert "Victus Victus" not in q
        assert "HP Victus 15-fa2352TX" in q


def test_build_queries_falls_back_when_sparse():
    target = LaptopReviewTarget(
        laptop_id="lap-99",
        canonical_id="dell-g15-5530",
    )
    queries = CommunityQueryBuilder().build_queries(target)

    assert len(queries) == 4
    assert queries[3] == "dell-g15-5530 review"


# ─── Platform-tailored queries ──────────────────────────────────────────────


def test_platform_queries_use_screen_size_and_sub_model():
    target = LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
        screen_size=15.0,
    )

    queries = CommunityQueryBuilder().build_platform_queries(target)

    assert queries.editorial == "Lenovo LOQ 15 review"
    assert queries.forum == "Lenovo 15IRX9"
    assert queries.regional == "LOQ 15IRX9"


def test_platform_forum_query_falls_back_without_sub_model():
    target = LaptopReviewTarget(
        laptop_id="lap-2",
        canonical_id="lenovo-yoga-7",
        brand="Lenovo",
        laptop_family="Yoga",
        screen_size=14.0,
    )

    queries = CommunityQueryBuilder().build_platform_queries(target)

    assert queries.forum == "Lenovo Yoga 14"
    assert queries.regional == "Yoga 14"


def test_platform_queries_truncate_screen_size_to_marketing_tier():
    target = LaptopReviewTarget(
        laptop_id="lap-3",
        canonical_id="hp-victus-15-fa2352tx",
        brand="HP",
        laptop_family="Victus",
        laptop_model="HP Victus 15-fa2352TX",
        screen_size=15.6,
    )

    queries = CommunityQueryBuilder().build_platform_queries(target)

    assert queries.editorial == "HP Victus 15 review"
    assert "FA2352TX" in queries.regional or "15-FA2352TX" in queries.regional
