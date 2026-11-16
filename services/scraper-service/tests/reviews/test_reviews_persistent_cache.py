"""Offline tests for the persistent cross-batch review evidence cache."""

from __future__ import annotations

import pytest

from app.common.cache import ICacheProvider, InMemoryCacheProvider
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import TranscriptSegment, YouTubeComment, YouTubeVideo
from app.services.reviews.cache import (
    ReviewsPersistentCache,
    community_json_cache_key,
    community_text_cache_key,
    normalize_cache_url,
    youtube_video_cache_key,
)
from app.services.reviews.community.arabhardware import ArabhardwarePlatformScraper
from app.services.reviews.community.collector import CommunitiesReviewsCollector
from app.services.reviews.community.http import get_json, get_text, shared_community_session
from app.services.reviews.community.laptopmag import LaptopMagPlatformScraper
from app.services.reviews.community.level1techs import Level1TechsPlatformScraper
from app.services.reviews.youtube.collector import YouTubeReviewsCollector


class FakeResponse:
    def __init__(self, text: str = "", json_data=None, status_code: int = 200):
        self.text = text
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data


class FakeClient:
    def __init__(self, routes=None, status_code: int = 200):
        self.routes = routes or {}
        self.status_code = status_code
        self.requested_urls: list[str] = []

    async def get(self, url, headers=None):
        self.requested_urls.append(url)
        for fragment, response in self.routes.items():
            if fragment in url:
                return response
        return FakeResponse(status_code=self.status_code)


class FakeSearchService:
    def __init__(self, videos, comments=None):
        self.videos = videos
        self.comments = comments if comments is not None else []
        self.search_calls: list[str] = []
        self.comment_calls = 0

    async def search_reviews(self, query: str):
        self.search_calls.append(query)
        return list(self.videos)

    async def fetch_top_comments(self, video_url: str):
        self.comment_calls += 1
        return list(self.comments)


class FakeTranscriptService:
    def __init__(self, result=("A full transcript about thermals.", [], "en", False)):
        self.result = result
        self.calls: list[str] = []

    async def fetch_transcript(self, video_id: str):
        self.calls.append(video_id)
        return self.result


class BrokenCacheProvider(ICacheProvider):
    async def get(self, key: str):
        raise ConnectionError("redis unreachable")

    async def set(self, key: str, value: bytes, ttl_seconds: int | None = None):
        raise ConnectionError("redis unreachable")

    async def set_nx(self, key: str, value: bytes, ttl_seconds: int = 86400):
        raise ConnectionError("redis unreachable")

    async def delete(self, key: str) -> None:
        raise ConnectionError("redis unreachable")

    async def clear_prefix(self, prefix: str) -> int:
        raise ConnectionError("redis unreachable")

    async def health_check(self) -> bool:
        return False


def _target() -> LaptopReviewTarget:
    return LaptopReviewTarget(
        laptop_id="lap-loq",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="15IRX9",
        screen_size=15.6,
    )


def _video_search_result(view_count: int = 100) -> dict:
    return {
        "video_id": "vid123",
        "title": "Lenovo LOQ 15IRX9 Review",
        "channel_name": "Laptop Reviews",
        "video_url": "https://www.youtube.com/watch?v=vid123",
        "view_count": view_count,
        "comments_deferred": True,
    }


def _comment() -> YouTubeComment:
    return YouTubeComment(
        comment_id="c1",
        author="owner",
        comment_text="Thermals are solid after undervolting.",
        like_count=12,
    )


@pytest.mark.anyio
async def test_youtube_collector_reuses_persistent_transcript_across_batches():
    provider = InMemoryCacheProvider()
    search_1 = FakeSearchService([_video_search_result(100)], comments=[_comment()])
    transcript_1 = FakeTranscriptService(
        (
            "Full thermals transcript.",
            [TranscriptSegment(start_seconds=0.0, text="Full thermals transcript.")],
            "en",
            False,
        )
    )
    collector_1 = YouTubeReviewsCollector(
        search_service=search_1,
        transcript_service=transcript_1,
        cache_provider=provider,
    )

    first = list((await collector_1.collect_for_targets([_target()])).values())[0]
    assert first.videos[0].transcript_text == "Full thermals transcript."
    assert transcript_1.calls == ["vid123"]
    assert search_1.comment_calls == 1

    search_2 = FakeSearchService([_video_search_result(999_999)], comments=[])
    transcript_2 = FakeTranscriptService()
    collector_2 = YouTubeReviewsCollector(
        search_service=search_2,
        transcript_service=transcript_2,
        cache_provider=provider,
    )

    second = list((await collector_2.collect_for_targets([_target()])).values())[0]
    video = second.videos[0]

    assert transcript_2.calls == []
    assert search_2.comment_calls == 0
    assert video.transcript_text == "Full thermals transcript."
    assert [comment.comment_id for comment in video.top_comments] == ["c1"]
    assert video.view_count == 999_999
    assert collector_2.cache_stats()["yt_hits"] == 1


@pytest.mark.anyio
async def test_youtube_collector_never_caches_empty_transcript():
    provider = InMemoryCacheProvider()
    search_1 = FakeSearchService([_video_search_result(100)], comments=[])
    transcript_1 = FakeTranscriptService(("", [], "en", False))
    collector_1 = YouTubeReviewsCollector(
        search_service=search_1,
        transcript_service=transcript_1,
        cache_provider=provider,
    )

    await collector_1.collect_for_targets([_target()])

    assert await provider.get(youtube_video_cache_key("vid123")) is None

    search_2 = FakeSearchService([_video_search_result(100)], comments=[])
    transcript_2 = FakeTranscriptService(("Now available.", [], "en", False))
    collector_2 = YouTubeReviewsCollector(
        search_service=search_2,
        transcript_service=transcript_2,
        cache_provider=provider,
    )

    result = list((await collector_2.collect_for_targets([_target()])).values())[0]
    assert transcript_2.calls == ["vid123"]
    assert result.videos[0].transcript_text == "Now available."


@pytest.mark.anyio
async def test_community_http_caches_article_pages_but_not_search_queries():
    provider = InMemoryCacheProvider()
    search_url = "https://example.com/search?q=loq"
    review_url = "https://example.com/review/loq"
    json_url = "https://forum.level1techs.com/posts/99.json"

    client_1 = FakeClient(
        routes={
            "/search": FakeResponse(text="search results"),
            "/review/": FakeResponse(text="<html>review body</html>"),
            "/posts/99.json": FakeResponse(json_data={"id": 99, "raw": "forum post"}),
        }
    )
    async with shared_community_session(cache_provider=provider):
        assert await get_text(client_1, search_url) == "search results"
        assert await get_text(client_1, review_url, persistent=True) == "<html>review body</html>"
        assert await get_json(client_1, json_url, persistent=True) == {"id": 99, "raw": "forum post"}

    client_2 = FakeClient(
        routes={
            "/search": FakeResponse(text="search results 2"),
            "/review/": FakeResponse(text="<html>review body 2</html>"),
            "/posts/99.json": FakeResponse(json_data={"id": 99, "raw": "forum post 2"}),
        }
    )
    async with shared_community_session(cache_provider=provider):
        assert await get_text(client_2, search_url) == "search results 2"
        assert await get_text(client_2, review_url, persistent=True) == "<html>review body</html>"
        assert await get_json(client_2, json_url, persistent=True) == {"id": 99, "raw": "forum post"}

    assert client_1.requested_urls == [search_url, review_url, json_url]
    assert client_2.requested_urls == [search_url]


@pytest.mark.anyio
async def test_community_http_never_caches_http_errors():
    provider = InMemoryCacheProvider()
    url = "https://example.com/review/failing"

    async with shared_community_session(cache_provider=provider):
        assert await get_text(FakeClient(status_code=500), url, persistent=True) is None

    assert await provider.get(community_text_cache_key(url)) is None

    client_2 = FakeClient(status_code=500)
    async with shared_community_session(cache_provider=provider):
        assert await get_text(client_2, url, persistent=True) is None

    assert client_2.requested_urls == [url]


@pytest.mark.anyio
async def test_platform_scrapers_mark_only_article_fetches_persistent():
    provider = InMemoryCacheProvider()
    target = _target()

    laptopmag_search = '<a href="/reviews/lenovo-loq-15-review">Lenovo LOQ 15 review</a>'
    laptopmag_review = """
    <html><body>
      <span class="rating">4.5 out of 5</span>
      <div class="reasons-to-buy"><ul><li>Great battery life</li></ul></div>
      <div class="verdict"><p>Excellent budget gaming laptop.</p></div>
    </body></html>
    """
    arab_search = """
    <html><body>
      <article>
        <h2><a href="/reviews/lenovo-loq-15irx9">مراجعة لابتوب Lenovo LOQ</a></h2>
        <p>تجربة استخدام كاملة مع قياس درجات الحرارة والأداء.</p>
      </article>
    </body></html>
    """
    arab_article = """
    <html><body>
      <div class="post-content">
        <p>الفقرة الأولى التفصيلية للمراجعة مع تقييم شامل لكافة الجوانب والمواصفات التقنية.</p>
      </div>
    </body></html>
    """
    level1_payload = {
        "topics": [{"id": 42, "slug": "lenovo-loq-experience", "title": "Lenovo LOQ experience"}],
        "posts": [
            {
                "id": 101,
                "topic_id": 42,
                "post_number": 1,
                "username": "owner42",
                "blurb": "My Lenovo 15IRX9 runs cool under load and the fans stay quiet.",
            }
        ],
    }
    level1_post = {
        "id": 101,
        "raw": "This is the full un-truncated post body explaining thermal performance in deep detail.",
    }

    scrapers_and_routes = [
        (
            LaptopMagPlatformScraper,
            {
                "/search?searchTerm=": FakeResponse(text=laptopmag_search),
                "/reviews/lenovo-loq-15-review": FakeResponse(text=laptopmag_review),
            },
            "/reviews/lenovo-loq-15-review",
        ),
        (
            ArabhardwarePlatformScraper,
            {
                "/search?s=": FakeResponse(text=arab_search),
                "/reviews/lenovo-loq-15irx9": FakeResponse(text=arab_article),
            },
            "/reviews/lenovo-loq-15irx9",
        ),
        (
            Level1TechsPlatformScraper,
            {
                "/search.json": FakeResponse(json_data=level1_payload),
                "/posts/101.json": FakeResponse(json_data=level1_post),
            },
            "/posts/101.json",
        ),
    ]

    for scraper_cls, routes, article_fragment in scrapers_and_routes:
        client_1 = FakeClient(routes=routes)
        async with shared_community_session(cache_provider=provider):
            await scraper_cls(http_client=client_1).scrape_for_target(target, ["query"])

        client_2 = FakeClient(routes=routes)
        async with shared_community_session(cache_provider=provider):
            await scraper_cls(http_client=client_2).scrape_for_target(target, ["query"])

        search_hits = [url for url in client_2.requested_urls if "/search" in url]
        article_hits = [url for url in client_2.requested_urls if article_fragment in url]
        assert search_hits, f"{scraper_cls.__name__} must refresh its search each session"
        assert article_hits == [], f"{scraper_cls.__name__} must reuse the cached article"


@pytest.mark.anyio
async def test_cache_failures_fail_open_without_aborting_collection(caplog):
    broken = BrokenCacheProvider()

    transcript = FakeTranscriptService(
        ("Live transcript.", [TranscriptSegment(start_seconds=0.0, text="Live transcript.")], "en", False)
    )
    youtube = YouTubeReviewsCollector(
        search_service=FakeSearchService([_video_search_result(10)], comments=[_comment()]),
        transcript_service=transcript,
        cache_provider=broken,
    )

    youtube_result = list((await youtube.collect_for_targets([_target()])).values())[0]
    assert youtube_result.videos[0].transcript_text == "Live transcript."
    assert "Review cache read failed" in caplog.text

    laptopmag_client = FakeClient(
        routes={
            "/search?searchTerm=": FakeResponse(
                text='<a href="/reviews/lenovo-loq-15-review">Lenovo LOQ 15 review</a>'
            ),
            "/reviews/lenovo-loq-15-review": FakeResponse(
                text='<html><body><div class="verdict"><p>Solid laptop.</p></div></body></html>'
            ),
        }
    )
    communities = CommunitiesReviewsCollector(
        scrapers=[LaptopMagPlatformScraper(http_client=laptopmag_client)],
        cache_provider=broken,
    )

    community_result = list((await communities.collect_for_targets([_target()])).values())[0]
    assert len(community_result.editorial) == 1
    assert "Community cache read failed" in caplog.text


@pytest.mark.anyio
async def test_cache_ttl_zero_disables_persistence():
    provider = InMemoryCacheProvider()
    cache = ReviewsPersistentCache(provider, youtube_ttl_seconds=0, community_ttl_seconds=0)

    video = YouTubeVideo(
        video_id="vid123",
        title="Review",
        video_url="https://www.youtube.com/watch?v=vid123",
        transcript_text="Transcript.",
    )
    url = "https://example.com/review/loq"

    await cache.set_youtube_video("vid123", video)
    await cache.set_text(url, "body")
    await cache.set_json(url, {"ok": True})

    assert await provider.get(youtube_video_cache_key("vid123")) is None
    assert await provider.get(community_text_cache_key(url)) is None
    assert await provider.get(community_json_cache_key(url)) is None

    await provider.set(youtube_video_cache_key("vid123"), b'{"transcript_text": "cached"}')
    await provider.set(community_text_cache_key(url), b"cached body")
    await provider.set(community_json_cache_key(url), b'{"cached": true}')

    assert await cache.get_youtube_video("vid123") is None
    assert await cache.get_text(url) is None
    assert await cache.get_json(url) is None
    assert cache.stats_summary() == {
        "yt_hits": 0,
        "yt_misses": 0,
        "yt_stores": 0,
        "http_hits": 0,
        "http_misses": 0,
        "http_stores": 0,
    }


def test_cache_key_and_url_normalization():
    assert youtube_video_cache_key("  vid123  ") == "reviews:yt:video:vid123"
    assert normalize_cache_url("  https://example.com/a?q=1  ") == "https://example.com/a?q=1"
    assert community_text_cache_key("https://example.com/a?q=1") != community_text_cache_key(
        "https://example.com/a?q=2"
    )
    assert community_text_cache_key("https://example.com/a").startswith("reviews:http:text:")
    assert community_json_cache_key("https://example.com/a").startswith("reviews:http:json:")
