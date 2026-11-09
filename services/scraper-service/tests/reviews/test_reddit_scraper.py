"""Unit tests for the Reddit platform scraper and 4-layer relevance gate."""

import pytest
from app.schemas.events import LaptopReviewTarget
from app.services.reviews.community.reddit import (
    DEFAULT_USER_AGENT,
    RedditPlatformScraper,
    SubTargets,
)


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data


class MockHttpClient:
    def __init__(self, search_posts=None, comments=None, status_code=200, raise_error=None):
        self.search_posts = search_posts or []
        self.comments = comments or []
        self.status_code = status_code
        self.raise_error = raise_error
        self.requested_urls = []

    async def get(self, url, headers=None):
        self.requested_urls.append(url)
        if self.raise_error:
            raise self.raise_error

        if "search.json" in url:
            return MockResponse(
                {"data": {"children": [{"data": p} for p in self.search_posts]}},
                status_code=self.status_code,
            )
        if ".json" in url:
            return MockResponse(
                [
                    {"data": {"children": []}},
                    {"data": {"children": [{"kind": "t1", "data": c} for c in self.comments]}},
                ],
                status_code=self.status_code,
            )
        return MockResponse({}, status_code=self.status_code)


def test_subtargets_enum_contains_expected_subreddits():
    expected = {
        "GamingLaptops",
        "SuggestALaptop",
        "laptops",
        "LenovoLegion",
        "ASUSROG",
        "AMDLaptops",
    }
    actual = {s.value for s in SubTargets}
    assert actual == expected


def test_model_tokens_extracts_chassis_codes_and_excludes_brands():
    target = LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
        skus=["83DV00E2US"],
        mpn="83DV00E2US",
    )
    tokens = RedditPlatformScraper._model_tokens(target)

    assert "15IRX9" in tokens
    assert "83DV00E2US" in tokens
    assert "LENOVO" not in tokens
    assert "LOQ" not in tokens


def test_model_tokens_handles_hyphenated_codes_and_excludes_screen_size():
    target = LaptopReviewTarget(
        laptop_id="lap-2",
        canonical_id="hp-victus-15-fa2352tx",
        brand="HP",
        laptop_family="Victus",
        laptop_model="HP Victus 15-fa2352TX",
    )
    tokens = RedditPlatformScraper._model_tokens(target)

    assert "15-FA2352TX" in tokens
    assert "FA2352TX" in tokens
    assert "15" not in tokens
    assert "HP" not in tokens
    assert "VICTUS" not in tokens


def test_fallback_terms_uses_cleaned_subject():
    target = LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
    )
    terms = RedditPlatformScraper._fallback_terms(target)

    assert "LENOVO LOQ 15IRX9" in terms
    assert "LOQ 15IRX9" in terms
    assert "LENOVO LOQ LOQ 15IRX9" not in terms


def test_relevance_gate_layer1_rejects_unrelated_brand_models():
    target = LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
    )
    tokens = RedditPlatformScraper._model_tokens(target)
    fallback = RedditPlatformScraper._fallback_terms(target)
    scraper = RedditPlatformScraper()

    unrelated_post = {
        "title": "Lenovo IdeaPad 3 overheating issue",
        "selftext": "My Lenovo IdeaPad has been getting very hot lately while doing basic office work.",
        "score": 15,
        "num_comments": 4,
    }
    relevant_post = {
        "title": "Lenovo LOQ 15IRX9 thermals and review",
        "selftext": "Detailed thermals for the LOQ 15IRX9 under full synthetic and gaming loads.",
        "score": 15,
        "num_comments": 4,
    }

    assert scraper._passes_gate(unrelated_post, tokens, fallback) is False
    assert scraper._passes_gate(relevant_post, tokens, fallback) is True


def test_relevance_gate_layer2_rejects_deal_posts():
    scraper = RedditPlatformScraper()
    tokens = {"15IRX9"}
    fallback = set()

    deal_posts = [
        {
            "title": "[Deal] Lenovo LOQ 15IRX9 $799",
            "selftext": "Clearance discount on BestBuy with promo coupon.",
            "num_comments": 5,
            "score": 20,
        },
        {
            "title": "Black Friday sale for LOQ 15IRX9",
            "selftext": "Massive price drop for anyone buying now.",
            "num_comments": 5,
            "score": 20,
        },
    ]

    for post in deal_posts:
        assert scraper._passes_gate(post, tokens, fallback) is False


def test_relevance_gate_layer3_rejects_insufficient_depth():
    scraper = RedditPlatformScraper(min_body_length=40, min_comments=2)
    tokens = {"15IRX9"}
    fallback = set()

    too_short = {
        "title": "LOQ 15IRX9 thoughts?",
        "selftext": "Is it good?",
        "num_comments": 5,
        "score": 10,
    }
    too_few_comments = {
        "title": "LOQ 15IRX9 detailed thermals test and benchmarks",
        "selftext": "This is a sufficiently long body describing all tests and cooling performance.",
        "num_comments": 1,
        "score": 10,
    }

    assert scraper._passes_gate(too_short, tokens, fallback) is False
    assert scraper._passes_gate(too_few_comments, tokens, fallback) is False


@pytest.mark.anyio
async def test_scrape_for_target_ranks_and_limits_posts():
    target = LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
    )

    posts_data = [
        {
            "id": f"p{i}",
            "title": f"Lenovo LOQ 15IRX9 test {i}",
            "selftext": "Detailed post body with sufficient character count explaining the laptop.",
            "score": i * 10,
            "num_comments": 5,
            "permalink": f"/r/GamingLaptops/comments/p{i}/",
            "url": f"https://reddit.com/r/GamingLaptops/comments/p{i}/",
            "author": f"user_{i}",
            "created_utc": 1700000000 + i,
        }
        for i in range(1, 6)
    ]

    client = MockHttpClient(search_posts=posts_data)
    scraper = RedditPlatformScraper(
        max_posts=2,
        http_client=client,
        request_delay_seconds=0.0,
        subreddits=(SubTargets.GAMING_LAPTOPS,),
    )

    results = await scraper.scrape_for_target(target, ["Lenovo LOQ 15IRX9 review"])

    assert len(results) == 2
    assert results[0].post_id == "p5"
    assert results[0].score == 50
    assert results[1].post_id == "p4"
    assert results[1].score == 40


@pytest.mark.anyio
async def test_fetch_comments_filters_deleted_and_short_replies():
    target = LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
    )

    search_posts = [
        {
            "id": "p1",
            "title": "Lenovo LOQ 15IRX9 review",
            "selftext": "Detailed substantive review about cooling, battery, and fan noise.",
            "score": 30,
            "num_comments": 3,
            "permalink": "/r/GamingLaptops/comments/p1/",
            "author": "main_author",
            "created_utc": 1700000000,
        }
    ]

    mock_comments = [
        {"id": "c1", "author": "[deleted]", "body": "This substantive comment was deleted by author.", "score": 5},
        {"id": "c2", "author": "user1", "body": "Nice", "score": 2},  # < 15 chars
        {
            "id": "c3",
            "author": "user2",
            "body": "I have the exact same model and temps are great around 70C.",
            "score": 10,
            "created_utc": 1700000500,
        },
    ]

    client = MockHttpClient(search_posts=search_posts, comments=mock_comments)
    scraper = RedditPlatformScraper(
        max_posts=1,
        http_client=client,
        request_delay_seconds=0.0,
        subreddits=(SubTargets.GAMING_LAPTOPS,),
    )

    results = await scraper.scrape_for_target(target, ["Lenovo LOQ 15IRX9 review"])

    assert len(results) == 1
    post = results[0]
    assert len(post.comments) == 1
    assert post.comments[0].comment_id == "c3"
    assert post.comments[0].author == "user2"
    assert post.comments[0].score == 10


@pytest.mark.anyio
async def test_fail_open_on_network_errors():
    target = LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
    )

    # 1. 403 status code
    client_403 = MockHttpClient(status_code=403)
    scraper = RedditPlatformScraper(http_client=client_403, request_delay_seconds=0.0)
    assert await scraper.scrape_for_target(target, ["Lenovo LOQ review"]) == []

    # 2. Network exception
    client_err = MockHttpClient(raise_error=ConnectionError("Reddit unreachable"))
    scraper_err = RedditPlatformScraper(http_client=client_err, request_delay_seconds=0.0)
    assert await scraper_err.scrape_for_target(target, ["Lenovo LOQ review"]) == []
