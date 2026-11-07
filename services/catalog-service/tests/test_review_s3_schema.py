"""Schema validation tests for the S3 chassis reviews artifact.

Verifies that a realistic ``raw_chassis_reviews_{batch_id}.json`` payload parses
into ``RawChassisReviewsFile`` and round-trips without loss.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.reviews_s3 import (
    BatchMetadata,
    BatchMetadataSummary,
    ChassisIdentity,
    CommunitiesData,
    CommunityComment,
    FacebookPost,
    LaptopChassisReviewItem,
    RawChassisReviewsFile,
    RedditPost,
    TranscriptSegment,
    YouTubeComment,
    YouTubeReviewData,
    YouTubeVideo,
)


def _sample_payload() -> dict:
    return {
        "batch_metadata": {
            "job_id": "reviews_batch_3f2a1b",
            "generated_at": "2026-11-07T10:15:00+00:00",
            "scraper_service_version": "1.2.0",
            "total_targets_processed": 2,
            "metrics_summary": {
                "total_youtube_videos": 3,
                "total_youtube_comments": 12,
                "total_community_posts": 2,
            },
        },
        "laptops": [
            {
                "chassis_key": "lenovo:loq:15IRX9",
                "primary_laptop_id": "8f14e45f-ceea-467a-9c1e-1d7c2a7f6b3a",
                "primary_canonical_id": "lenovo-loq-15irx9-16gb",
                "matched_laptop_ids": [
                    "8f14e45f-ceea-467a-9c1e-1d7c2a7f6b3a",
                    "1c383cd3-0e3a-4b1e-9a3b-2f8d5c6e7a91",
                ],
                "matched_canonical_ids": [
                    "lenovo-loq-15irx9-16gb",
                    "lenovo-loq-15irx9-32gb",
                ],
                "identity": {
                    "brand": "Lenovo",
                    "laptop_family": "LOQ",
                    "laptop_model": "LOQ 15IRX9",
                    "sub_model": "15IRX9",
                    "aggregated_mpns": ["83DV01HSED", "83DV01HTED"],
                    "aggregated_skus": ["83DV01HSED", "83DV01HTED"],
                },
                "youtube": {
                    "query_used": "Lenovo LOQ 15IRX9 review",
                    "total_videos_found": 2,
                    "videos": [
                        {
                            "video_id": "abc123xyz",
                            "title": "Lenovo LOQ 15IRX9 Review - Best Budget Gaming Laptop?",
                            "channel_name": "Jarrod's Tech",
                            "channel_url": "https://youtube.com/@JarrodsTech",
                            "video_url": "https://youtube.com/watch?v=abc123xyz",
                            "published_at": "2026-08-01T00:00:00+00:00",
                            "duration_seconds": 903,
                            "view_count": 512000,
                            "language": "en",
                            "is_auto_generated_captions": False,
                            "transcript_text": "Today we are looking at the Lenovo LOQ...",
                            "transcript_segments": [
                                {"start_seconds": 0.0, "text": "Today we are looking at"},
                                {"start_seconds": 2.5, "text": "the Lenovo LOQ 15IRX9."},
                            ],
                            "top_comments": [
                                {
                                    "comment_id": "Ugx1abc",
                                    "author": "GamerDude",
                                    "comment_text": "Thermals look great for the price.",
                                    "like_count": 128,
                                    "published_at": "2026-08-02T12:00:00+00:00",
                                }
                            ],
                        }
                    ],
                },
                "communities": {
                    "reddit": [
                        {
                            "post_id": "t3_xyz789",
                            "subreddit": "GamingLaptops",
                            "post_title": "LOQ 15IRX9 owner impressions after 3 months",
                            "post_url": "https://reddit.com/r/GamingLaptops/xyz789",
                            "author": "loq_owner",
                            "published_at": "2026-09-01T00:00:00+00:00",
                            "score": 342,
                            "post_body": "Bought this in June, here are my thoughts...",
                            "comments": [
                                {
                                    "comment_id": "t1_aaa111",
                                    "author": "replier",
                                    "comment_text": "How is the fan noise?",
                                    "score": 12,
                                    "published_at": "2026-09-01T05:00:00+00:00",
                                }
                            ],
                        }
                    ],
                    "facebook": [
                        {
                            "group_name": "Egypt Laptop Deals",
                            "post_url": "https://facebook.com/groups/eglaptops/posts/123",
                            "author": "Ahmed M.",
                            "published_at": "2026-09-10T00:00:00+00:00",
                            "comment_text": "Bought the LOQ, very happy with performance.",
                            "reaction_count": 47,
                        }
                    ],
                },
            },
            {
                "chassis_key": "asus:tuf-gaming:FA608PM",
                "primary_laptop_id": "4a8b1c2d-3e4f-5a6b-7c8d-9e0f1a2b3c4d",
                "primary_canonical_id": "asus-tuf-a16-fa608pm",
                "matched_laptop_ids": ["4a8b1c2d-3e4f-5a6b-7c8d-9e0f1a2b3c4d"],
                "matched_canonical_ids": ["asus-tuf-a16-fa608pm"],
                "identity": {
                    "brand": "ASUS",
                    "laptop_family": "TUF Gaming",
                    "laptop_model": "FA608PM-RV169W",
                    "sub_model": "FA608PM",
                    "aggregated_mpns": ["90NR0MC1-M008A0"],
                    "aggregated_skus": ["90NR0MC1-M008A0"],
                },
            },
        ],
    }


def test_raw_chassis_reviews_file_parses_full_payload():
    parsed = RawChassisReviewsFile.model_validate(_sample_payload())

    assert parsed.batch_metadata.job_id == "reviews_batch_3f2a1b"
    assert parsed.batch_metadata.scraper_service_version == "1.2.0"
    assert parsed.batch_metadata.metrics_summary.total_youtube_videos == 3
    assert parsed.batch_metadata.metrics_summary.total_community_posts == 2
    assert parsed.batch_metadata.generated_at == datetime(2026, 11, 7, 10, 15, tzinfo=UTC)

    assert len(parsed.laptops) == 2

    loq = parsed.laptops[0]
    assert loq.chassis_key == "lenovo:loq:15IRX9"
    assert loq.matched_laptop_ids == [
        "8f14e45f-ceea-467a-9c1e-1d7c2a7f6b3a",
        "1c383cd3-0e3a-4b1e-9a3b-2f8d5c6e7a91",
    ]
    assert loq.identity.aggregated_mpns == ["83DV01HSED", "83DV01HTED"]
    assert loq.youtube.total_videos_found == 2
    assert len(loq.youtube.videos) == 1
    assert loq.youtube.videos[0].transcript_segments[1].start_seconds == 2.5
    assert loq.youtube.videos[0].top_comments[0].like_count == 128
    assert loq.communities.reddit[0].comments[0].comment_text == "How is the fan noise?"
    assert loq.communities.facebook[0].reaction_count == 47

    # Second item omits youtube/communities entirely; defaults must apply.
    tuf = parsed.laptops[1]
    assert tuf.youtube.videos == []
    assert tuf.youtube.total_videos_found == 0
    assert tuf.communities.reddit == []
    assert tuf.communities.facebook == []


def test_raw_chassis_reviews_file_round_trip_is_lossless():
    parsed = RawChassisReviewsFile.model_validate(_sample_payload())

    dumped = parsed.model_dump(mode="json")
    restored = RawChassisReviewsFile.model_validate(dumped)

    assert restored == parsed


def test_batch_metadata_defaults_scraper_version_and_summary():
    meta = BatchMetadata(
        job_id="job-1",
        generated_at=datetime.now(UTC),
        total_targets_processed=0,
    )

    assert meta.scraper_service_version == "1.0.0"
    assert meta.metrics_summary == BatchMetadataSummary()


def test_laptop_item_defaults_are_empty_collections():
    item = LaptopChassisReviewItem(
        chassis_key="generic:unknown",
        primary_laptop_id="lap-1",
        primary_canonical_id="canonical-1",
    )

    assert item.matched_laptop_ids == []
    assert item.matched_canonical_ids == []
    assert item.identity == ChassisIdentity()
    assert item.youtube == YouTubeReviewData()
    assert item.communities == CommunitiesData()


def test_communities_supports_multiple_platforms_independently():
    data = CommunitiesData(
        reddit=[
            RedditPost(
                post_id="p1",
                subreddit="GamingLaptops",
                post_title="Title",
                post_url="https://reddit.com/p1",
            )
        ],
        facebook=[FacebookPost(comment_text="Nice laptop")],
    )

    assert len(data.reddit) == 1
    assert data.reddit[0].post_body == ""
    assert data.reddit[0].comments == []
    assert len(data.facebook) == 1
    assert data.facebook[0].group_name is None


def test_youtube_video_defaults_and_nested_models():
    video = YouTubeVideo(video_id="v1", title="Review", video_url="https://youtube.com/v1")

    assert video.language == "en"
    assert video.is_auto_generated_captions is False
    assert video.transcript_text == ""
    assert video.transcript_segments == []
    assert video.top_comments == []

    enriched = YouTubeVideo(
        video_id="v2",
        title="Review 2",
        video_url="https://youtube.com/v2",
        transcript_segments=[TranscriptSegment(start_seconds=1.0, text="hello")],
        top_comments=[YouTubeComment(comment_id="c1", comment_text="great")],
    )
    assert enriched.transcript_segments[0].text == "hello"
    assert enriched.top_comments[0].author is None


def test_published_at_accepts_datetime_or_string():
    with_string = YouTubeVideo(
        video_id="v1",
        title="t",
        video_url="https://youtube.com/v1",
        published_at="2026-01-01",
    )
    assert with_string.published_at == "2026-01-01"

    with_dt = YouTubeVideo(
        video_id="v2",
        title="t",
        video_url="https://youtube.com/v2",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert isinstance(with_dt.published_at, datetime)


def test_missing_required_fields_raise_validation_error():
    with pytest.raises(ValidationError):
        RawChassisReviewsFile.model_validate({"laptops": []})  # no batch_metadata

    with pytest.raises(ValidationError):
        LaptopChassisReviewItem(chassis_key="x")  # missing primary ids


def test_shared_community_comment_contract():
    comment = CommunityComment(
        comment_id="c1",
        author="someone",
        comment_text="text",
        score=5,
        published_at="2026-01-01",
    )
    assert comment.score == 5
    assert comment.published_at == "2026-01-01"
