"""Unit tests for the top-level ReviewCollectorService orchestrator."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.schemas.events import LaptopReviewTarget, ScrapeReviewsCommand, ScrapeReviewsPayload
from app.schemas.reviews_s3 import (
    CommunitiesData,
    RawChassisReviewsFile,
    RedditPost,
    YouTubeReviewData,
    YouTubeVideo,
)
from app.services.reviews.collector import ReviewCollectorService
from app.services.reviews.contracts import (
    ICommunitiesReviewsCollector,
    IYouTubeReviewsCollector,
)


class FakeYouTubeCollector(IYouTubeReviewsCollector):
    async def collect_for_targets(self, targets):
        results = {}
        for t in targets:
            key = f"{t.brand.lower()}:{t.laptop_family.lower()}:{t.laptop_model.lower()}"
            results[key] = YouTubeReviewData(
                query_used=f"{t.brand} {t.laptop_model} review",
                total_videos_found=1,
                videos=[
                    YouTubeVideo(
                        video_id="vid123",
                        title=f"{t.laptop_model} In-Depth Review",
                        video_url="https://youtube.com/watch?v=vid123",
                        transcript_text="Great cooling and solid performance.",
                    )
                ],
            )
        return results


class FakeCommunitiesCollector(ICommunitiesReviewsCollector):
    async def collect_for_targets(self, targets):
        results = {}
        for t in targets:
            key = f"{t.brand.lower()}:{t.laptop_family.lower()}:{t.laptop_model.lower()}"
            results[key] = CommunitiesData(
                reddit=[
                    RedditPost(
                        post_id="post_red_1",
                        subreddit="GamingLaptops",
                        post_title=f"{t.laptop_model} thermals discussion",
                        post_url="https://reddit.com/r/GamingLaptops/post_red_1",
                        score=35,
                    )
                ]
            )
        return results


@pytest.mark.anyio
async def test_process_reviews_batch_merges_and_uploads():
    target = LaptopReviewTarget(
        laptop_id="lap-loq",
        canonical_id="lenovo-loq-15irx9",
        brand="Lenovo",
        laptop_family="LOQ",
        laptop_model="15irx9",
        skus=["83DV00E2US"],
        mpn="83DV00E2US",
    )
    cmd = ScrapeReviewsCommand(
        payload=ScrapeReviewsPayload(
            job_id="job-test-123",
            targets=[target],
        )
    )

    storage_mock = MagicMock()
    storage_mock.upload_json = MagicMock(return_value="reviews/raw_chassis_reviews_job-test-123.json")
    broker_mock = AsyncMock()

    service = ReviewCollectorService(
        storage_service=storage_mock,
        broker=broker_mock,
        youtube_collector=FakeYouTubeCollector(),
        communities_collector=FakeCommunitiesCollector(),
    )

    s3_key = await service.process_reviews_batch(cmd)

    assert s3_key == "reviews/raw_chassis_reviews_job-test-123.json"
    storage_mock.upload_json.assert_called_once()
    broker_mock.publish.assert_awaited_once()

    # Verify uploaded content adheres to RawChassisReviewsFile
    call_kwargs = storage_mock.upload_json.call_args.kwargs
    uploaded_data = call_kwargs["data"]
    uploaded_file = RawChassisReviewsFile.model_validate(uploaded_data)
    assert uploaded_file.batch_metadata.job_id == "job-test-123"
    assert uploaded_file.batch_metadata.total_targets_processed == 1
    assert uploaded_file.batch_metadata.metrics_summary.total_youtube_videos == 1
    assert uploaded_file.batch_metadata.metrics_summary.total_community_posts == 1

    item = uploaded_file.laptops[0]
    assert len(item.youtube.videos) == 1
    assert len(item.communities.reddit) == 1
    assert item.communities.reddit[0].post_id == "post_red_1"
