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
