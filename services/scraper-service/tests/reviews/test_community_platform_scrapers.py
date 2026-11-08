"""Unit tests for the three community platform scrapers and their wiring.

All clients are injected fakes, so these tests never touch the network and
verify the fail-open contract explicitly.
"""

from __future__ import annotations

import pytest

from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import CommunitiesData, CommunityPost, EditorialReview
from app.services.reviews.community.arabhardware import ArabhardwarePlatformScraper
from app.services.reviews.community.collector import CommunitiesReviewsCollector
from app.services.reviews.community.contracts import ICommunityPlatformScraper
from app.services.reviews.community.laptopmag import LaptopMagPlatformScraper
from app.services.reviews.community.level1techs import Level1TechsPlatformScraper


class FakeResponse:
    def __init__(self, text: str = "", json_data=None, status_code: int = 200):
        self.text = text
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data


class FakeClient:
    """Route requests by URL substring; every call is recorded."""

    def __init__(self, routes=None, status_code: int = 200, raise_error: Exception | None = None):
        self.routes = routes or {}
        self.status_code = status_code
        self.raise_error = raise_error
        self.requested_urls: list[str] = []

    async def get(self, url, headers=None):
        self.requested_urls.append(url)
        if self.raise_error:
            raise self.raise_error
        for fragment, response in self.routes.items():
            if fragment in url:
                return response
        return FakeResponse(status_code=self.status_code)


def _target() -> LaptopReviewTarget:
    return LaptopReviewTarget(
        laptop_id="lap-1",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="LOQ 15IRX9",
        screen_size=15.0,
    )


# ─── Laptop Mag ─────────────────────────────────────────────────────────────

_LAPTOPMAG_SEARCH_HTML = """
<html><body>
  <a href="/news/some-news">News</a>
  <a href="/reviews/lenovo-loq-15-review">Lenovo LOQ 15 review</a>
</body></html>
"""

_LAPTOPMAG_REVIEW_HTML = """
<html><body>
  <span class="rating">4.5 out of 5</span>
  <div class="reasons-to-buy"><ul><li>Great battery life</li><li>Solid build</li></ul></div>
  <div class="reasons-to-avoid"><ul><li>Heavy chassis</li></ul></div>
  <div class="verdict"><p>Excellent budget gaming laptop.</p></div>
</body></html>
"""


@pytest.mark.anyio
async def test_laptopmag_extracts_editorial_review():
    client = FakeClient(
        routes={
            "/search?searchTerm=": FakeResponse(text=_LAPTOPMAG_SEARCH_HTML),
            "/reviews/lenovo-loq-15-review": FakeResponse(text=_LAPTOPMAG_REVIEW_HTML),
        }
    )
    scraper = LaptopMagPlatformScraper(http_client=client)

    reviews = await scraper.scrape_for_target(_target(), ["aspect query"])

    assert len(reviews) == 1
    review = reviews[0]
    assert isinstance(review, EditorialReview)
    assert review.source == "laptopmag"
    assert review.review_url == "https://www.laptopmag.com/reviews/lenovo-loq-15-review"
    assert review.rating == 4.5
    assert review.pros == ["Great battery life", "Solid build"]
    assert review.cons == ["Heavy chassis"]
    assert review.verdict == "Excellent budget gaming laptop."
    assert "Lenovo+LOQ+15+review" in client.requested_urls[0]


@pytest.mark.anyio
async def test_laptopmag_fails_open():
    raising = FakeClient(raise_error=ConnectionError("unreachable"))
    assert await LaptopMagPlatformScraper(http_client=raising).scrape_for_target(_target(), []) == []

    broken = FakeClient(status_code=503)
    assert await LaptopMagPlatformScraper(http_client=broken).scrape_for_target(_target(), []) == []


# ─── Level1Techs ────────────────────────────────────────────────────────────

_LEVEL1TECHS_PAYLOAD = {
    "topics": [{"id": 42, "slug": "lenovo-loq-experience", "title": "Lenovo LOQ experience"}],
    "posts": [
        {
            "id": 101,
            "topic_id": 42,
            "post_number": 1,
            "username": "owner42",
            "blurb": "My Lenovo 15IRX9 runs cool under load and the fans stay quiet.",
            "created_at": "2026-01-02T10:00:00Z",
        },
        {
            "id": 102,
            "topic_id": 42,
            "post_number": 2,
            "username": "dealer",
            "blurb": "Big sale on the 15IRX9 right now with a promo coupon and discount.",
        },
        {
            "id": 103,
            "topic_id": 42,
            "post_number": 3,
            "username": "short",
            "blurb": "15IRX9 good",
        },
        {
            "id": 104,
            "topic_id": 42,
            "post_number": 4,
            "username": "other",
            "blurb": "Completely unrelated thread about a desktop workstation and its cooling.",
        },
    ],
}


@pytest.mark.anyio
async def test_level1techs_applies_three_layer_gate():
    client = FakeClient(routes={"/search.json": FakeResponse(json_data=_LEVEL1TECHS_PAYLOAD)})
    scraper = Level1TechsPlatformScraper(http_client=client)

    posts = await scraper.scrape_for_target(_target(), ["aspect query"])

    assert [post.post_id for post in posts] == ["101"]
    post = posts[0]
    assert isinstance(post, CommunityPost)
    assert post.platform == "level1techs"
    assert post.author == "owner42"
    assert post.post_title == "Lenovo LOQ experience"
    assert post.post_url == "https://forum.level1techs.com/t/lenovo-loq-experience/42/1"
    assert "15IRX9" in client.requested_urls[0]


@pytest.mark.anyio
async def test_level1techs_fails_open():
    raising = FakeClient(raise_error=TimeoutError("slow"))
    assert await Level1TechsPlatformScraper(http_client=raising).scrape_for_target(_target(), []) == []

    malformed = FakeClient(routes={"/search.json": FakeResponse(json_data=["not", "a", "dict"])})
    assert await Level1TechsPlatformScraper(http_client=malformed).scrape_for_target(_target(), []) == []


# ─── Arabhardware ──────────────────────────────────────────────────────────

_ARABHARDWARE_SEARCH_HTML = """
<html><body>
  <article>
    <h2><a href="/reviews/lenovo-loq-15irx9">مراجعة لابتوب Lenovo LOQ</a></h2>
    <p>تجربة استخدام كاملة مع قياس درجات الحرارة والأداء.</p>
  </article>
  <article>
    <h3><a href="https://forum.arabhardware.net/threads/loq">نقاش مستخدمي LOQ</a></h3>
    <p>آراء المستخدمين حول البطارية والمروحة.</p>
  </article>
</body></html>
"""


@pytest.mark.anyio
async def test_arabhardware_extracts_discussion_snippets():
    client = FakeClient(routes={"/search?q=": FakeResponse(text=_ARABHARDWARE_SEARCH_HTML)})
    scraper = ArabhardwarePlatformScraper(http_client=client)

    posts = await scraper.scrape_for_target(_target(), ["aspect query"])

    assert len(posts) == 2
    assert all(isinstance(post, CommunityPost) for post in posts)
    assert posts[0].platform == "arabhardware"
    assert posts[0].post_title == "مراجعة لابتوب Lenovo LOQ"
    assert posts[0].post_url == "https://arabhardware.net/reviews/lenovo-loq-15irx9"
    assert posts[0].post_body == "تجربة استخدام كاملة مع قياس درجات الحرارة والأداء."
    assert posts[1].post_url == "https://forum.arabhardware.net/threads/loq"
    assert posts[1].post_id


@pytest.mark.anyio
async def test_arabhardware_fails_open():
    raising = FakeClient(raise_error=ConnectionError("unreachable"))
    assert await ArabhardwarePlatformScraper(http_client=raising).scrape_for_target(_target(), []) == []


# ─── Collector mapping ──────────────────────────────────────────────────────

class FakeEditorialScraper(ICommunityPlatformScraper):
    platform_name = "editorial-fake"

    async def scrape_for_target(self, laptop_target, queries):
        return [
            EditorialReview(source="editorial-fake", review_url="https://example.com/review", rating=4.0),
        ]


class FakeDiscussionScraper(ICommunityPlatformScraper):
    platform_name = "forum-fake"

    async def scrape_for_target(self, laptop_target, queries):
        return [
            CommunityPost(platform="forum-fake", post_id="d1", post_title="Duplicate id"),
            CommunityPost(platform="forum-fake", post_id="d1", post_title="Duplicate id"),
            CommunityPost(platform="forum-fake", post_id="d2", post_title="Unique"),
        ]


@pytest.mark.anyio
async def test_collector_maps_editorial_and_discussions():
    collector = CommunitiesReviewsCollector(
        scrapers=[FakeEditorialScraper(), FakeDiscussionScraper()]
    )

    results = await collector.collect_for_targets([_target()])
    data = next(iter(results.values()))

    assert isinstance(data, CommunitiesData)
    assert [review.review_url for review in data.editorial] == ["https://example.com/review"]
    assert sorted(post.post_id for post in data.discussions) == ["d1", "d2"]
    assert data.reddit == []
    assert data.facebook == []


def test_collector_defaults_to_the_three_community_scrapers():
    collector = CommunitiesReviewsCollector()

    assert [scraper.platform_name for scraper in collector.scrapers] == [
        "laptopmag",
        "level1techs",
        "arabhardware",
    ]
