"""Strongly-typed schema for the S3 chassis reviews artifact.

The scraper-service writes ``raw_chassis_reviews_{batch_id}.json`` to object
storage after collecting YouTube and community reviews for every chassis in a
batch. The catalog-service reads the same file back, so this module must stay in
100% lockstep with its counterpart in the other service.

Clean Architecture note: this is a pure serialization contract. It has no
database or network dependencies and can be validated in isolation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ─── Batch metadata ─────────────────────────────────────────────────────────


class BatchMetadataSummary(BaseModel):
    """Aggregate counts describing the review collection run."""

    total_youtube_videos: int = 0
    total_youtube_comments: int = 0
    total_community_posts: int = 0


class BatchMetadata(BaseModel):
    """Top-level provenance for one generated reviews artifact."""

    job_id: str
    generated_at: datetime
    scraper_service_version: str = "1.0.0"
    total_targets_processed: int
    metrics_summary: BatchMetadataSummary = Field(default_factory=BatchMetadataSummary)


# ─── YouTube ────────────────────────────────────────────────────────────────


class YouTubeComment(BaseModel):
    """A single comment left under a YouTube review video."""

    comment_id: str
    author: str | None = None
    comment_text: str
    like_count: int | None = None
    published_at: datetime | str | None = None


class TranscriptSegment(BaseModel):
    """One timed caption segment from a YouTube video transcript."""

    start_seconds: float
    text: str


class YouTubeVideo(BaseModel):
    """A single YouTube review video with transcript and top comments."""

    video_id: str
    title: str
    channel_name: str | None = None
    channel_url: str | None = None
    video_url: str
    published_at: datetime | str | None = None
    duration_seconds: int | None = None
    view_count: int | None = None
    language: str = "en"
    is_auto_generated_captions: bool = False
    transcript_text: str = ""
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
    top_comments: list[YouTubeComment] = Field(default_factory=list)


class YouTubeReviewData(BaseModel):
    """All YouTube evidence collected for one chassis."""

    query_used: str | None = None
    total_videos_found: int = 0
    videos: list[YouTubeVideo] = Field(default_factory=list)


# ─── Community platforms ────────────────────────────────────────────────────


class CommunityComment(BaseModel):
    """A comment on a community platform post (e.g. a Reddit reply)."""

    comment_id: str | None = None
    author: str | None = None
    comment_text: str
    score: int | None = None
    published_at: datetime | str | None = None


class RedditPost(BaseModel):
    """A Reddit discussion thread about a chassis."""

    post_id: str
    subreddit: str
    post_title: str
    post_url: str
    author: str | None = None
    published_at: datetime | str | None = None
    score: int | None = None
    post_body: str = ""
    comments: list[CommunityComment] = Field(default_factory=list)


class FacebookPost(BaseModel):
    """A Facebook group post about a chassis."""

    group_name: str | None = None
    post_url: str | None = None
    author: str | None = None
    published_at: datetime | str | None = None
    comment_text: str
    reaction_count: int | None = None


class CommunitiesData(BaseModel):
    """Community platform evidence for one chassis.

    New platforms (e.g. X, TikTok, forums) are added as additional optional
    list fields with ``default_factory=list`` so the contract stays backward
    compatible: older artifacts simply deserialize with an empty list.
    """

    reddit: list[RedditPost] = Field(default_factory=list)
    facebook: list[FacebookPost] = Field(default_factory=list)


# ─── Per-chassis review item ────────────────────────────────────────────────


class ChassisIdentity(BaseModel):
    """Identity fields describing the chassis and its aggregated SKUs."""

    brand: str | None = None
    laptop_family: str | None = None
    laptop_model: str | None = None
    sub_model: str | None = None
    aggregated_mpns: list[str] = Field(default_factory=list)
    aggregated_skus: list[str] = Field(default_factory=list)


class LaptopChassisReviewItem(BaseModel):
    """Complete review payload for one resolved chassis."""

    chassis_key: str
    primary_laptop_id: str
    primary_canonical_id: str
    matched_laptop_ids: list[str] = Field(default_factory=list)
    matched_canonical_ids: list[str] = Field(default_factory=list)
    identity: ChassisIdentity = Field(default_factory=ChassisIdentity)
    youtube: YouTubeReviewData = Field(default_factory=YouTubeReviewData)
    communities: CommunitiesData = Field(default_factory=CommunitiesData)


class RawChassisReviewsFile(BaseModel):
    """Root schema of ``raw_chassis_reviews_{batch_id}.json``."""

    batch_metadata: BatchMetadata
    laptops: list[LaptopChassisReviewItem] = Field(default_factory=list)


__all__ = [
    "BatchMetadata",
    "BatchMetadataSummary",
    "ChassisIdentity",
    "CommunitiesData",
    "CommunityComment",
    "FacebookPost",
    "LaptopChassisReviewItem",
    "RawChassisReviewsFile",
    "RedditPost",
    "TranscriptSegment",
    "YouTubeComment",
    "YouTubeReviewData",
    "YouTubeVideo",
]
