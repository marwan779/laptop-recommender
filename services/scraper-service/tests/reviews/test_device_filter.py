"""Unit tests for non-laptop device filtering and YouTube video deduplication."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from app.schemas.events import LaptopReviewTarget
from app.services.reviews.chassis_key import build_chassis_key
from app.services.reviews.community.filters import is_non_laptop_device
from app.services.reviews.youtube.collector import YouTubeReviewsCollector


@pytest.mark.parametrize(
    "title",
    [
        "ASUS TUF GAMING B860M-PLUS WIFI Motherboard Review",
        "Nintendo Switch 2: Everything we know",
        "Acer Nitro XV271U 27-inch Gaming Monitor Review",
        "Acer Nitro N50-640 Gaming Desktop PC Review",
        "ASUS TUF Gaming GeForce RTX 5070 OC 12GB Review",
        "ASUS ROG Strix GeForce RTX 5080 OC Edition Review",
        "Lenovo Legion Go S Handheld Console",
    ],
)
def test_rejects_non_laptop_devices(title: str):
    assert is_non_laptop_device(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "ASUS TUF Gaming A16 FA608 (2025) Review",
        "Acer Nitro V 15 ANV15-52 Gaming Laptop Review",
        "Lenovo LOQ 15IRX10 RTX 4060 Gaming Laptop",
        "ASUS ROG Strix G16 RTX 5070 Review",
        "HP Omen 16 RTX 4070 Review",
        "Acer Nitro V 15 RTX 4060 Review",
    ],
)
def test_accepts_valid_laptops(title: str):
    assert is_non_laptop_device(title) is False


@pytest.mark.parametrize(
    "title",
    [
        "ASUS ROG Strix 32” 1440P USB-C Curved HDR400 Gaming Monitor (XG32WCMS) QHD 280Hz",
        "Samsung Odyssey G7 27-inch Curved Gaming Monitor 240Hz",
        "MSI GeForce RTX 4070 Ti SUPER 16G GAMING X SLIM Graphics Card",
        "ASUS ROG Ally X (2024) RC72LA Handheld Gaming Console",
        "Apple iPad Pro 11-inch M4 chip Standard glass 256GB Wi-Fi",
    ],
)
def test_rejects_devices_in_body_text(title: str):
    assert is_non_laptop_device("Hands-on impressions", title) is True


def test_accepts_internal_laptop_display_and_gpu_wording():
    assert is_non_laptop_device(
        "Lenovo Legion 5 review",
        "The 15.6-inch screen is bright; the laptop RTX 4060 GPU handles games.",
    ) is False


def _target(model: str, canonical_id: str) -> LaptopReviewTarget:
    return LaptopReviewTarget(
        laptop_id=f"lap-{canonical_id}",
        canonical_id=canonical_id,
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model=model,
    )


@pytest.mark.anyio
async def test_youtube_collector_deduplicates_video_across_targets():
    shared_video = {
        "video_id": "vid123",
        "title": "Lenovo LOQ 15IRX10 In-Depth Review",
        "channel_name": "Reviewer",
        "channel_url": "https://youtube.com/@reviewer",
        "video_url": "https://www.youtube.com/watch?v=vid123",
        "published_at": "2026-01-01",
        "duration_seconds": 900,
        "view_count": 12345,
        "top_comments": [],
    }

    search_service = AsyncMock()
    search_service.search_reviews = AsyncMock(return_value=[shared_video])

    transcript_service = AsyncMock()
    transcript_service.fetch_transcript = AsyncMock(
        return_value=("Shared transcript text", [], "en", False)
    )

    collector = YouTubeReviewsCollector(
        search_service=search_service,
        transcript_service=transcript_service,
    )

    targets = [
        _target("LOQ 15IRX10", "lenovo-loq-15irx10"),
        _target("LOQ 15IRX9", "lenovo-loq-15irx9"),
    ]

    results = await collector.collect_for_targets(targets)

    transcript_service.fetch_transcript.assert_awaited_once_with("vid123")
    assert len(results) == 2

    for target in targets:
        data = results[build_chassis_key(target)]
        assert data.total_videos_found == 1
        assert len(data.videos) == 1
        video = data.videos[0]
        assert video.video_id == "vid123"
        assert video.transcript_text == "Shared transcript text"
        assert video.title == shared_video["title"]
