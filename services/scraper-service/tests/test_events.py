"""Unit tests for RabbitMQ event and command schemas in scraper-service."""

import uuid
from app.price_monitor.models import PriceCheckItem, PriceCheckItemResult
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
            s3_key="raw-catalogs/2026-11-05/catalog.json",
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
                    new_price_egp=33000.0,
                    old_in_stock=True,
                    new_in_stock=True,
                    has_changed=True,
                )
            ],
        )
    )
    assert evt.event_type == EventType.PRICES_CHECKED_EVENT
    assert evt.payload.results[0].new_price_egp == 33000.0


def test_reviews_command_and_ready_serialization():
    cmd = ScrapeReviewsCommand(
        payload=ScrapeReviewsPayload(
            job_id=str(uuid.uuid4()),
            targets=[
                LaptopReviewTarget(
                    laptop_id="lap-1",
                    canonical_id="laptop_lenovo_loq_83dv01hsed_16gb_512gb",
                    search_queries=["Lenovo LOQ 83DV01HSED review Reddit"],
                )
            ],
        )
    )
    assert cmd.event_type == EventType.REVIEWS_SCRAPE_COMMAND
    assert len(cmd.payload.targets) == 1

    evt = ReviewsReadyEvent(
        payload=ReviewsReadyPayload(
            job_id=cmd.payload.job_id,
            total_laptops=1,
            total_snippets=2,
            results=[
                LaptopReviewsResult(
                    laptop_id="lap-1",
                    canonical_id="laptop_lenovo_loq_83dv01hsed_16gb_512gb",
                    snippets=[
                        LaptopReviewSnippet(
                            source="reddit",
                            title="Great budget gaming laptop",
                            url="https://reddit.com/r/Lenovo/123",
                            snippet_text="Thermals are great, battery life around 4 hours.",
                            score_or_upvotes=45,
                        ),
                        LaptopReviewSnippet(
                            source="youtube",
                            title="Lenovo LOQ Review 2024",
                            url="https://youtube.com/watch?v=abc",
                            snippet_text="The 100% sRGB screen is fantastic for the price.",
                        ),
                    ],
                )
            ],
        )
    )
    assert evt.event_type == EventType.REVIEWS_READY_EVENT
    assert len(evt.payload.results[0].snippets) == 2
