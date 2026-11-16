"""Pure domain tests for extracting and normalizing laptop review source links."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.domain.reviews.sources import (
    ReviewSourceItem,
    extract_review_sources,
    normalize_review_sources_collection,
)


def test_sources_domain_module_has_no_framework_or_db_imports():
    sources_path = Path(__file__).resolve().parent.parent / "app" / "domain" / "reviews" / "sources.py"
    tree = ast.parse(sources_path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])

    forbidden = {"sqlalchemy", "asyncpg", "psycopg", "fastapi", "starlette", "httpx", "requests"}
    assert imported_modules.isdisjoint(forbidden)


def test_extract_review_sources_from_format_a_v6_payload():
    v6_item = {
        "youtube": {
            "videos": [
                {
                    "title": "Lenovo Legion 5 Pro Review",
                    "channel_name": "Jarrod'sTech",
                    "channel_url": "https://www.youtube.com/@JarrodsTech",
                    "video_url": "https://www.youtube.com/watch?v=abc123",
                    "view_count": 250000,
                    "published_at": "2025-04-12T15:30:00Z",
                },
                {
                    "title": "Duplicate Trailing Slash",
                    "video_url": "https://www.youtube.com/watch?v=abc123/",
                    "view_count": 10,
                },
                {
                    "title": "Lower Views Clip",
                    "channel_name": "Reviewer B",
                    "video_url": "https://www.youtube.com/watch?v=xyz999",
                    "view_count": 12000,
                },
                {
                    "title": "Bad URL",
                    "video_url": "ftp://invalid.example.com/file",
                },
            ]
        },
        "communities": {
            "editorial": [
                {
                    "source": "Notebookcheck",
                    "review_url": "https://www.notebookcheck.net/legion-review.99.0.html",
                    "rating": 88.5,
                    "verdict": "Best-in-class display and cooling.",
                }
            ],
            "discussions": [
                {
                    "platform": "level1techs",
                    "author": "alice",
                    "post_title": "Linux support thread",
                    "post_url": "https://forum.level1techs.com/t/legion/123",
                    "score": 19,
                    "published_at": "2025-03-01T10:00:00Z",
                },
                {
                    "platform": "reddit",
                    "author": "bob",
                    "post_title": "6 months battery review",
                    "post_url": "https://www.reddit.com/r/GamingLaptops/comments/xyz",
                    "score": 45,
                },
            ],
        },
    }

    sources = extract_review_sources(v6_item)
    assert [s.source_type for s in sources] == [
        "editorial",
        "youtube",
        "youtube",
        "community",
        "community",
    ]
    assert sources[0].platform == "notebookcheck"
    assert sources[0].rating == 88.5
    assert sources[1].title == "Lenovo Legion 5 Pro Review"
    assert sources[1].score_or_views == 250000
    assert sources[1].published_at == datetime(2025, 4, 12, 15, 30, tzinfo=UTC)
    assert sources[2].title == "Lower Views Clip"
    assert sources[3].platform == "reddit"
    assert sources[3].score_or_views == 45
    assert sources[4].platform == "level1techs"


def test_extract_review_sources_from_format_b2_and_chunk_fallback():
    b2_item = {
        "review_sources": [
            {
                "source_type": "youtube",
                "platform": "youtube",
                "title": "B2 Video",
                "url": "https://www.youtube.com/watch?v=b2vid",
                "author_or_channel": "Tech Channel",
                "score_or_views": 5000,
            }
        ],
        "deduplicated_chunks": [
            {"source_type": "scraped_youtube_transcript", "source_url": "https://www.youtube.com/watch?v=ignored"}
        ],
    }
    sources = extract_review_sources(b2_item)
    assert len(sources) == 1
    assert sources[0].url == "https://www.youtube.com/watch?v=b2vid"

    chunk_only_item = {
        "deduplicated_chunks": [
            {"source_type": "scraped_youtube_transcript", "source_url": "https://www.youtube.com/watch?v=chunk1"},
            {"source_type": "scraped_discussion", "source_url": "https://www.reddit.com/r/laptops/comments/1"},
            {"source_type": "scraped_discussion", "source_url": "https://www.reddit.com/r/laptops/comments/1/"},
        ]
    }
    fallback_sources = extract_review_sources(chunk_only_item)
    assert [s.source_type for s in fallback_sources] == ["youtube", "community"]


def test_normalize_review_sources_collection_accepts_orm_like_objects():
    orm_like = SimpleNamespace(
        source_type="youtube",
        platform="youtube",
        title="Mock ORM Video",
        url="https://www.youtube.com/watch?v=orm1",
        author_or_channel="Channel One",
        channel_url="https://www.youtube.com/@c1",
        rating=None,
        score_or_views=1234,
        published_at=None,
    )
    normalized = normalize_review_sources_collection([orm_like])
    assert len(normalized) == 1
    assert isinstance(normalized[0], ReviewSourceItem)
    assert normalized[0].to_dict()["url"] == "https://www.youtube.com/watch?v=orm1"
