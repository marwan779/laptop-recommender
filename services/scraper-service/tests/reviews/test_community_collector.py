"""Unit tests for the CommunitiesReviewsCollector coordinator."""

import pytest
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import CommunityPost, EditorialReview
from app.services.reviews.chassis_key import build_chassis_key
from app.services.reviews.community.collector import CommunitiesReviewsCollector
from app.services.reviews.community.contracts import ICommunityPlatformScraper


class FakeForumScraper(ICommunityPlatformScraper):
    platform_name = "level1techs"

    def __init__(self, posts_by_target=None, raise_on_target=None):
        self.posts_by_target = posts_by_target or {}
        self.raise_on_target = raise_on_target

    async def scrape_for_target(self, laptop_target, queries):
        if self.raise_on_target == laptop_target.canonical_id:
            raise RuntimeError("Fake forum failure")
        return self.posts_by_target.get(laptop_target.canonical_id, [])


class FakeEditorialScraper(ICommunityPlatformScraper):
    platform_name = "laptopmag"

    def __init__(self, reviews=None):
        self.reviews = reviews or []

    async def scrape_for_target(self, laptop_target, queries):
        return self.reviews


@pytest.mark.anyio
async def test_collect_for_targets_returns_pattern_b_keyed_dict():
    t1 = LaptopReviewTarget(
        laptop_id="l1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
    )
    t2 = LaptopReviewTarget(
        laptop_id="l2",
        canonical_id="asus-tuf-gaming-a15-fa507nv",
        brand="ASUS",
        laptop_family="TUF Gaming",
        laptop_model="TUF Gaming A15 FA507NV",
    )

    forum_post = CommunityPost(
        platform="level1techs",
        post_id="f1",
        post_title="Lenovo LOQ thermals",
        post_url="https://forum.level1techs.com/t/1",
    )
    ed_review = EditorialReview(
        source="LaptopMag",
        review_url="https://www.laptopmag.com/reviews/loq",
        verdict="Great thermals on the LOQ",
    )

    scraper_forum = FakeForumScraper(posts_by_target={"lenovo-loq-15irx9": [forum_post]})
    scraper_ed = FakeEditorialScraper(reviews=[ed_review])

    collector = CommunitiesReviewsCollector(scrapers=[scraper_forum, scraper_ed])
    results = await collector.collect_for_targets([t1, t2])

    assert len(results) == 2
    chassis_keys = list(results.keys())
    assert any("lenovo" in k and "15irx9" in k for k in chassis_keys)
    assert any("asus" in k and "fa507nv" in k for k in chassis_keys)

    loq_key = [k for k in chassis_keys if "15irx9" in k][0]
    loq_data = results[loq_key]
    assert len(loq_data.discussions) == 1
    assert loq_data.discussions[0].post_id == "f1"
    assert len(loq_data.editorial) == 1

    tuf_key = [k for k in chassis_keys if "fa507nv" in k][0]
    tuf_data = results[tuf_key]
    assert len(tuf_data.discussions) == 0


@pytest.mark.anyio
async def test_deduplicates_discussions_by_platform_and_post_id():
    target = LaptopReviewTarget(
        laptop_id="l1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
    )
    p1 = CommunityPost(platform="level1techs", post_id="dup_id", post_title="Title 1", post_url="url1", score=10)
    p2 = CommunityPost(platform="level1techs", post_id="dup_id", post_title="Title 2", post_url="url2", score=5)
    p3 = CommunityPost(platform="arabhardware", post_id="unique_id", post_title="Title 3", post_url="url3", score=20)

    scraper = FakeForumScraper(posts_by_target={"lenovo-loq-15irx9": [p1, p2, p3]})
    collector = CommunitiesReviewsCollector(scrapers=[scraper])

    results = await collector.collect_for_targets([target])
    chassis_key = next(iter(results.keys()))
    posts = results[chassis_key].discussions

    assert len(posts) == 2
    assert [p.post_id for p in posts] == ["dup_id", "unique_id"]
    assert posts[0].post_title == "Title 1"


@pytest.mark.anyio
async def test_scraper_failure_isolation():
    t_failing = LaptopReviewTarget(
        laptop_id="l1",
        canonical_id="failing-chassis",
        brand="BrandA",
        laptop_model="ModelA",
    )
    t_working = LaptopReviewTarget(
        laptop_id="l2",
        canonical_id="working-chassis",
        brand="BrandB",
        laptop_model="ModelB",
    )

    good_post = CommunityPost(platform="level1techs", post_id="g1", post_title="Good", post_url="url_g")
    scraper = FakeForumScraper(
        posts_by_target={"working-chassis": [good_post]},
        raise_on_target="failing-chassis",
    )

    collector = CommunitiesReviewsCollector(scrapers=[scraper])
    results = await collector.collect_for_targets([t_failing, t_working])

    key_fail = build_chassis_key(t_failing)
    key_work = build_chassis_key(t_working)

    assert len(results) == 2
    assert results[key_fail].discussions == []
    assert len(results[key_work].discussions) == 1
    assert results[key_work].discussions[0].post_id == "g1"
