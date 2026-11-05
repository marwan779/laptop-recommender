"""Unit tests for RabbitMQ event and command schemas in catalog-service."""

import uuid

from app.schemas.events import (
    CatalogReadyEvent,
    CatalogReadyPayload,
    CatalogScrapeFailedEvent,
    CatalogScrapeFailedPayload,
    CheckPricesCommand,
    CheckPricesPayload,
    EventType,
    LaptopReviewSnippet,
    LaptopReviewsResult,
    LaptopReviewTarget,
    PricesCheckedEvent,
    PricesCheckedPayload,
    ReviewsReadyEvent,
    ReviewsReadyPayload,
    ScrapeCatalogCommand,
    ScrapeCatalogPayload,
    ScrapeReviewsCommand,
    ScrapeReviewsPayload,
)
from app.schemas.price_sync import PriceChangeType, PriceCheckItem, PriceCheckItemResult


def test_catalog_scrape_command_serialization():
    cmd = ScrapeCatalogCommand(
        payload=ScrapeCatalogPayload(
            batch_id=str(uuid.uuid4()),
            targets=["compumarts", "sigma"],
            level=2,
            until_models=["Lenovo Legion Pro 5"],
            force_full_crawl=False,
            upload_to_bucket=True,
        )
    )
    data = cmd.model_dump()
    assert data["event_type"] == EventType.CATALOG_SCRAPE_COMMAND
    assert data["payload"]["targets"] == ["compumarts", "sigma"]
    assert data["payload"]["level"] == 2
    assert "event_id" in data
    assert "timestamp" in data

    # Deserialization round-trip
    restored = ScrapeCatalogCommand.model_validate(data)
    assert restored.payload.batch_id == cmd.payload.batch_id


def test_catalog_ready_event_serialization():
    evt = CatalogReadyEvent(
        payload=CatalogReadyPayload(
            batch_id=str(uuid.uuid4()),
            s3_bucket="laptop-recommender-raw-catalog",
            s3_key="catalogs/catalog_12345.json",
            total_laptops=142,
            pointers_found={"compumarts": ["LOQ 15"], "sigma": ["TUF A15"]},
            duration_seconds=185.5,
        )
    )
    data = evt.model_dump()
    assert data["event_type"] == EventType.CATALOG_READY_EVENT
    assert data["payload"]["total_laptops"] == 142
    assert data["payload"]["s3_bucket"] == "laptop-recommender-raw-catalog"

    restored = CatalogReadyEvent.model_validate(data)
    assert restored.payload.pointers_found["compumarts"] == ["LOQ 15"]


def test_catalog_scrape_failed_event_serialization():
    evt = CatalogScrapeFailedEvent(
        payload=CatalogScrapeFailedPayload(
            batch_id=str(uuid.uuid4()),
            error_message="Network connection timeout connecting to store endpoints",
        )
    )
    assert evt.event_type == EventType.CATALOG_SCRAPE_FAILED_EVENT
    assert "Network connection timeout" in evt.payload.error_message


def test_check_prices_command_and_result_serialization():
    cmd = CheckPricesCommand(
        payload=CheckPricesPayload(
            batch_id=str(uuid.uuid4()),
            store_key="compumarts",
            items=[
                PriceCheckItem(
                    offer_id="off-1",
                    laptop_id="lap-1",
                    product_url="https://compumarts.com/p1",
                    current_price_egp=35000.0,
                    current_in_stock=True,
                )
            ],
        )
    )
    assert cmd.event_type == EventType.PRICES_CHECK_COMMAND
    assert len(cmd.payload.items) == 1

    evt = PricesCheckedEvent(
        payload=PricesCheckedPayload(
            batch_id=cmd.payload.batch_id,
            store_key="compumarts",
            total_items=1,
            changed_items_count=1,
            price_drops_count=1,
            results=[
                PriceCheckItemResult(
                    offer_id="off-1",
                    laptop_id="lap-1",
                    product_url="https://compumarts.com/p1",
                    old_price_egp=35000.0,
                    new_price_egp=33500.0,
                    old_in_stock=True,
                    new_in_stock=True,
                    has_changed=True,
                    change_type=PriceChangeType.PRICE_DROP,
                    price_delta_egp=-1500.0,
                    http_status=200,
                )
            ],
        )
    )
    assert evt.event_type == EventType.PRICES_CHECKED_EVENT
    assert evt.payload.results[0].new_price_egp == 33500.0
    assert evt.payload.results[0].change_type == PriceChangeType.PRICE_DROP


def test_reviews_command_and_ready_event_serialization():
    cmd = ScrapeReviewsCommand(
        payload=ScrapeReviewsPayload(
            job_id="job-rec-99",
            targets=[
                LaptopReviewTarget(
                    laptop_id="lap-123",
                    canonical_id="lenovo-legion-pro-5-16irx8",
                    search_queries=["Lenovo Legion Pro 5 review Reddit", "Legion Pro 5 YouTube review"],
                )
            ],
        )
    )
    assert cmd.event_type == EventType.REVIEWS_SCRAPE_COMMAND
    assert cmd.payload.targets[0].canonical_id == "lenovo-legion-pro-5-16irx8"

    evt = ReviewsReadyEvent(
        payload=ReviewsReadyPayload(
            job_id="job-rec-99",
            total_laptops=1,
            total_snippets=2,
            results=[
                LaptopReviewsResult(
                    laptop_id="lap-123",
                    canonical_id="lenovo-legion-pro-5-16irx8",
                    snippets=[
                        LaptopReviewSnippet(
                            source="reddit",
                            title="Legion Pro 5 long term review",
                            url="https://reddit.com/r/GamingLaptops/123",
                            snippet_text="Thermals are fantastic under high workload.",
                            score_or_upvotes=45,
                        ),
                        LaptopReviewSnippet(
                            source="youtube",
                            title="Jarrod's Tech Review",
                            url="https://youtube.com/watch?v=123",
                            snippet_text="Screen brightness exceeds 500 nits.",
                            score_or_upvotes=1200,
                        ),
                    ],
                )
            ],
        )
    )
    assert evt.event_type == EventType.REVIEWS_READY_EVENT
    assert len(evt.payload.results[0].snippets) == 2
    assert evt.payload.results[0].snippets[0].score_or_upvotes == 45
