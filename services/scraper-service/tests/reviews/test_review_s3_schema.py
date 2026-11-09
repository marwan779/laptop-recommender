"""Serialization tests for the S3 chassis reviews artifact written by the scraper.

The scraper-service is the *producer* of ``raw_chassis_reviews_{batch_id}.json``,
so these tests emphasize building the model in Python, serializing to JSON, and
reading it back. The schema must remain identical to the catalog-service copy.
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


def _build_reviews_file() -> RawChassisReviewsFile:
    return RawChassisReviewsFile(
        batch_metadata=BatchMetadata(
            job_id="reviews_batch_abc123",
            generated_at=datetime(2026, 11, 7, 9, 30, tzinfo=UTC),
            scraper_service_version="1.2.0",
            total_targets_processed=1,
            metrics_summary=BatchMetadataSummary(
                total_youtube_videos=1,
                total_youtube_comments=1,
                total_community_posts=1,
            ),
        ),
        laptops=[
            LaptopChassisReviewItem(
                chassis_key="lenovo:loq:15IRX9",
                primary_laptop_id="lap-uuid-1",
                primary_canonical_id="lenovo-loq-15irx9-16gb",
                matched_laptop_ids=["lap-uuid-1", "lap-uuid-2"],
                matched_canonical_ids=[
                    "lenovo-loq-15irx9-16gb",
                    "lenovo-loq-15irx9-32gb",
                ],
                identity=ChassisIdentity(
                    brand="Lenovo",
                    laptop_family="LOQ",
                    laptop_model="LOQ 15IRX9",
                    sub_model="15IRX9",
                    aggregated_mpns=["83DV01HSED", "83DV01HTED"],
                    aggregated_skus=["83DV01HSED", "83DV01HTED"],
                ),
                youtube=YouTubeReviewData(
                    query_used="Lenovo LOQ 15IRX9 review",
                    total_videos_found=1,
                    videos=[
                        YouTubeVideo(
                            video_id="vid1",
                            title="Lenovo LOQ 15IRX9 Review",
                            channel_name="Jarrod's Tech",
                            channel_url="https://youtube.com/@JarrodsTech",
                            video_url="https://youtube.com/watch?v=vid1",
                            published_at=datetime(2026, 8, 1, tzinfo=UTC),
                            duration_seconds=600,
                            view_count=10000,
                            transcript_text="Full transcript...",
                            transcript_segments=[
                                TranscriptSegment(start_seconds=0.0, text="Intro"),
                                TranscriptSegment(start_seconds=3.2, text="Specs"),
                            ],
                            top_comments=[
                                YouTubeComment(
                                    comment_id="c1",
                                    author="viewer",
                                    comment_text="Great review",
                                    like_count=10,
                                )
                            ],
                        )
                    ],
                ),
                communities=CommunitiesData(
                    reddit=[
                        RedditPost(
                            post_id="p1",
                            subreddit="GamingLaptops",
                            post_title="LOQ impressions",
                            post_url="https://reddit.com/p1",
                            score=42,
                            comments=[
                                CommunityComment(
                                    comment_id="cc1",
                                    author="replier",
                                    comment_text="Thanks for sharing",
                                    score=3,
                                )
                            ],
                        )
                    ],
                    facebook=[
                        FacebookPost(
                            group_name="Egypt Laptop Deals",
                            post_url="https://facebook.com/groups/x/posts/1",
                            author="Ahmed",
                            comment_text="Happy with it",
                            reaction_count=15,
                        )
                    ],
                ),
            )
        ],
    )


def test_reviews_file_serializes_to_json():
    model = _build_reviews_file()

    json_text = model.model_dump_json()
    assert '"chassis_key":"lenovo:loq:15IRX9"' in json_text
    assert '"matched_laptop_ids":["lap-uuid-1","lap-uuid-2"]' in json_text
    assert '"aggregated_mpns":["83DV01HSED","83DV01HTED"]' in json_text
    assert '"facebook"' in json_text
    assert '"reddit"' in json_text


def test_reviews_file_json_round_trip_is_lossless():
    model = _build_reviews_file()

    first_json = model.model_dump_json()
    restored = RawChassisReviewsFile.model_validate_json(first_json)

    # The `datetime | str` union coerces string timestamps to datetime on parse,
    # so losslessness is asserted on the canonical JSON representation.
    assert restored.model_dump_json() == first_json
    assert restored.batch_metadata.metrics_summary.total_youtube_comments == 1
    assert restored.laptops[0].matched_canonical_ids == [
        "lenovo-loq-15irx9-16gb",
        "lenovo-loq-15irx9-32gb",
    ]
    assert restored.laptops[0].youtube.videos[0].transcript_segments[1].start_seconds == 3.2


def test_published_at_accepts_string_and_datetime():
    as_string = YouTubeVideo(
        video_id="v1",
        title="t",
        video_url="https://youtube.com/v1",
        published_at="2026-01-01",
    )
    assert as_string.published_at == "2026-01-01"

    as_datetime = YouTubeVideo(
        video_id="v2",
        title="t",
        video_url="https://youtube.com/v2",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert isinstance(as_datetime.published_at, datetime)


def test_minimal_payload_defaults_are_applied():
    model = RawChassisReviewsFile(
        batch_metadata=BatchMetadata(
            job_id="job-min",
            generated_at=datetime.now(UTC),
            total_targets_processed=0,
        )
    )

    assert model.laptops == []
    assert model.batch_metadata.scraper_service_version == "1.0.0"
    assert model.batch_metadata.metrics_summary == BatchMetadataSummary()


def test_item_without_evidence_serializes_empty_structures():
    item = LaptopChassisReviewItem(
        chassis_key="generic:unknown",
        primary_laptop_id="lap-1",
        primary_canonical_id="canonical-1",
    )
    model = RawChassisReviewsFile(
        batch_metadata=BatchMetadata(
            job_id="job-empty",
            generated_at=datetime.now(UTC),
            total_targets_processed=1,
        ),
        laptops=[item],
    )

    data = model.model_dump(mode="json")
    laptop = data["laptops"][0]

    assert laptop["youtube"]["videos"] == []
    assert laptop["communities"]["reddit"] == []
    assert laptop["communities"]["facebook"] == []
    assert laptop["matched_laptop_ids"] == []


def test_communities_accepts_new_platforms_without_breaking_existing_shape():
    """Adding a platform must stay additive: reddit/facebook keep working."""
    data = CommunitiesData.model_validate(
        {
            "reddit": [
                {
                    "post_id": "p1",
                    "subreddit": "r/one",
                    "post_title": "t",
                    "post_url": "https://reddit.com/p1",
                }
            ],
            "facebook": [{"comment_text": "hi"}],
        }
    )

    assert data.reddit[0].post_id == "p1"
    assert data.facebook[0].comment_text == "hi"

    # Unknown keys are ignored rather than crashing an older consumer.
    tolerant = CommunitiesData.model_validate({"reddit": [], "facebook": [], "twitter": [{"id": 1}]})
    assert tolerant.reddit == []
    assert tolerant.facebook == []


def test_invalid_payload_raises_validation_error():
    with pytest.raises(ValidationError):
        RawChassisReviewsFile.model_validate({})

    with pytest.raises(ValidationError):
        YouTubeVideo(title="missing video id and url")
