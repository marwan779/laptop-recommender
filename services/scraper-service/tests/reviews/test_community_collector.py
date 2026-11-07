"""Unit tests for the CommunitiesReviewsCollector coordinator."""

import pytest
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import FacebookPost, RedditPost
from app.services.reviews.chassis_key import build_chassis_key
from app.services.reviews.community.collector import CommunitiesReviewsCollector
from app.services.reviews.community.contracts import ICommunityPlatformScraper


class FakeRedditScraper(ICommunityPlatformScraper):
    platform_name = "reddit"

    def __init__(self, posts_by_target=None, raise_on_target=None):
        self.posts_by_target = posts_by_target or {}
        self.raise_on_target = raise_on_target

    async def scrape_for_target(self, laptop_target, queries):
        if self.raise_on_target == laptop_target.canonical_id:
            raise RuntimeError("Fake Reddit failure")
        return self.posts_by_target.get(laptop_target.canonical_id, [])


class FakeFacebookScraper(ICommunityPlatformScraper):
    platform_name = "facebook"

    def __init__(self, posts=None):
        self.posts = posts or []

    async def scrape_for_target(self, laptop_target, queries):
        return self.posts


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

    reddit_post1 = RedditPost(
        post_id="r1",
        subreddit="GamingLaptops",
        post_title="Lenovo LOQ thermals",
        post_url="https://reddit.com/r1",
    )
    fb_post1 = FacebookPost(
        group_name="Egypt Laptop Deals",
        post_url="https://facebook.com/groups/1/p1",
        comment_text="Great thermals on the LOQ",
    )

    scraper_reddit = FakeRedditScraper(posts_by_target={"lenovo-loq-15irx9": [reddit_post1]})
    scraper_fb = FakeFacebookScraper(posts=[fb_post1])

    collector = CommunitiesReviewsCollector(scrapers=[scraper_reddit, scraper_fb])
    results = await collector.collect_for_targets([t1, t2])

    assert len(results) == 2
    # Chassis key check
    chassis_keys = list(results.keys())
    assert any("lenovo" in k and "15irx9" in k for k in chassis_keys)
    assert any("asus" in k and "fa507nv" in k for k in chassis_keys)

    # Content check for t1
    loq_key = [k for k in chassis_keys if "15irx9" in k][0]
    loq_data = results[loq_key]
    assert len(loq_data.reddit) == 1
    assert loq_data.reddit[0].post_id == "r1"
    assert len(loq_data.facebook) == 1

    # Content check for t2 (empty)
    tuf_key = [k for k in chassis_keys if "fa507nv" in k][0]
    tuf_data = results[tuf_key]
    assert len(tuf_data.reddit) == 0


@pytest.mark.anyio
async def test_deduplicates_posts_by_post_id():
    target = LaptopReviewTarget(
        laptop_id="l1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
    )
    p1 = RedditPost(post_id="dup_id", subreddit="GamingLaptops", post_title="Title 1", post_url="url1", score=10)
    p2 = RedditPost(post_id="dup_id", subreddit="SuggestALaptop", post_title="Title 2", post_url="url2", score=5)
    p3 = RedditPost(post_id="unique_id", subreddit="laptops", post_title="Title 3", post_url="url3", score=20)

    scraper = FakeRedditScraper(posts_by_target={"lenovo-loq-15irx9": [p1, p2, p3]})
    collector = CommunitiesReviewsCollector(scrapers=[scraper])

    results = await collector.collect_for_targets([target])
    chassis_key = next(iter(results.keys()))
    posts = results[chassis_key].reddit

    assert len(posts) == 2
    post_ids = [p.post_id for p in posts]
    assert post_ids == ["dup_id", "unique_id"]
    assert posts[0].post_title == "Title 1"  # Keeps the first occurrence


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

    good_post = RedditPost(post_id="g1", subreddit="laptops", post_title="Good", post_url="url_g")
    scraper = FakeRedditScraper(
        posts_by_target={"working-chassis": [good_post]},
        raise_on_target="failing-chassis",
    )

    collector = CommunitiesReviewsCollector(scrapers=[scraper])
    results = await collector.collect_for_targets([t_failing, t_working])

    key_fail = build_chassis_key(t_failing)
    key_work = build_chassis_key(t_working)

    assert len(results) == 2
    # Failing target safely gets empty CommunitiesData
    assert results[key_fail].reddit == []

    # Working target still succeeds
    assert len(results[key_work].reddit) == 1
    assert results[key_work].reddit[0].post_id == "g1"
