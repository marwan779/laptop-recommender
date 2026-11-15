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
    CommunityPost,
    EditorialReview,
    LaptopChassisReviewItem,
    RawChassisReviewsFile,
    TranscriptSegment,
    YouTubeComment,
    YouTubeReviewData,
    YouTubeVideo,
)


def _build_reviews_file() -> RawChassisReviewsFile:
    return RawChassisReviewsFile(
        batch_metadata=BatchMetadata(
            job_id="reviews_batch_abc123",
            generated_at=datetime(2026, 11, 7, 10, 15, tzinfo=UTC),
            total_targets_processed=1,
            metrics_summary=BatchMetadataSummary(
                total_youtube_videos=2,
                total_youtube_comments=1,
                total_community_posts=2,
            ),
        ),
        laptops=[
            LaptopChassisReviewItem(
                chassis_key="lenovo:loq:15IRX9",
                primary_laptop_id="lap-uuid-1",
                primary_canonical_id="lenovo-loq-15irx9-83dv01hsed",
                matched_laptop_ids=["lap-uuid-1", "lap-uuid-2"],
                matched_canonical_ids=[
                    "lenovo-loq-15irx9-83dv01hsed",
                    "lenovo-loq-15irx9-83dv01hted",
                ],
                identity=ChassisIdentity(
                    brand="Lenovo",
                    laptop_family="LOQ",
                    laptop_model="LOQ 15IRX9",
                    sub_model="15IRX9",
                    aggregated_mpns=["83DV01HSED", "83DV01HTED"],
                    aggregated_skus=["SKU-1", "SKU-2"],
                ),
                youtube=YouTubeReviewData(
                    query_used="Lenovo LOQ 15IRX9 review",
                    total_videos_found=2,
                    videos=[
                        YouTubeVideo(
                            video_id="dQw4w9WgXcQ",
                            title="Lenovo LOQ 15IRX9 Review",
                            channel_name="Jarrod'sTech",
                            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                            duration_seconds=900,
                            view_count=50000,
                            transcript_text="Solid thermals for a budget gaming laptop.",
                            transcript_segments=[
                                TranscriptSegment(
                                    start_seconds=12.4,
                                    text="Solid thermals for a budget gaming laptop.",
                                )
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
                    editorial=[
                        EditorialReview(
                            source="LaptopMag",
                            review_url="https://www.laptopmag.com/reviews/loq-15",
                            rating=4.0,
                            pros=["Strong thermals"],
                            cons=["Heavy chassis"],
                            verdict="Great budget gamer.",
                        )
                    ],
                    discussions=[
                        CommunityPost(
                            platform="level1techs",
                            post_id="p1",
                            post_title="LOQ impressions",
                            post_url="https://forum.level1techs.com/t/p1",
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
    assert '"editorial"' in json_text
    assert '"discussions"' in json_text


def test_reviews_file_json_round_trip_is_lossless():
    model = _build_reviews_file()

    first_json = model.model_dump_json()
    restored = RawChassisReviewsFile.model_validate_json(first_json)

    assert restored.model_dump_json() == first_json
    assert restored.batch_metadata.metrics_summary.total_youtube_comments == 1
    assert len(restored.laptops[0].communities.editorial) == 1
    assert restored.laptops[0].communities.discussions[0].comments[0].comment_text == "Thanks for sharing"


def test_minimal_payload_validates_with_sane_defaults():
    item = LaptopChassisReviewItem(
        chassis_key="lenovo:loq",
        primary_laptop_id="lap-1",
        primary_canonical_id="canonical-1",
    )
    model = RawChassisReviewsFile(
        batch_metadata=BatchMetadata(
            job_id="job-min",
            generated_at=datetime.now(UTC),
            total_targets_processed=1,
        ),
        laptops=[item],
    )

    data = model.model_dump(mode="json")
    laptop = data["laptops"][0]

    assert laptop["youtube"]["videos"] == []
    assert laptop["communities"]["editorial"] == []
    assert laptop["communities"]["discussions"] == []
    assert laptop["matched_laptop_ids"] == []


def test_communities_accepts_new_platforms_without_breaking_existing_shape():
    data = CommunitiesData.model_validate(
        {
            "editorial": [
                {
                    "source": "LaptopMag",
                    "review_url": "https://laptopmag.com/r1",
                    "verdict": "Solid choice",
                }
            ],
            "discussions": [
                {
                    "platform": "level1techs",
                    "post_id": "p1",
                    "post_title": "t",
                    "post_url": "https://forum.level1techs.com/t/p1",
                }
            ],
        }
    )

    assert data.editorial[0].source == "LaptopMag"
    assert data.discussions[0].post_id == "p1"

    tolerant = CommunitiesData.model_validate({"editorial": [], "discussions": [], "future_platform": [{"id": 1}]})
    assert tolerant.editorial == []
    assert tolerant.discussions == []


def test_invalid_payload_raises_validation_error():
    with pytest.raises(ValidationError):
        RawChassisReviewsFile.model_validate({})

    with pytest.raises(ValidationError):
        YouTubeVideo(title="missing video id and url")
