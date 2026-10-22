import pytest
from unittest.mock import MagicMock

from app.schemas.laptop import RetailerProduct
from app.stores.base import BaseStoreScraper
from app.pipeline.catalog_pipeline import GenericCatalogPipeline
from app.pipeline.schema import RawScrapedProduct


class ConcreteTestStoreScraper(BaseStoreScraper):
    @property
    def store_name(self) -> str:
        return "TestStore"

    @property
    def store_key(self) -> str:
        return "test_store"

    @property
    def base_url(self) -> str:
        return "https://teststore.com"

    def scrape_catalog(self, *args, **kwargs):
        return []

    def search_candidates(self, query: str, limit: int = 5):
        return []


def test_base_store_scraper_should_skip_card_rejects_accessories():
    scraper = ConcreteTestStoreScraper()
    assert scraper.should_skip_card("Lenovo 15.6 Laptop Everyday Backpack B210 Black") is True
    assert len(scraper.skipped_laptops) == 1
    assert scraper.skipped_laptops[0].stage == "card_filter"
    assert "non_laptop:accessory" in scraper.skipped_laptops[0].reason


def test_base_store_scraper_should_skip_card_accepts_valid_laptop():
    scraper = ConcreteTestStoreScraper()
    assert (
        scraper.should_skip_card(
            "ASUS Vivobook 16 X1605VA Intel Core i7-13620H 16GB 512GB",
            url="https://teststore.com/products/asus-vivobook-16",
        )
        is False
    )
    assert len(scraper.skipped_laptops) == 0


def test_base_store_scraper_should_skip_pdp_rejects_used_condition():
    scraper = ConcreteTestStoreScraper()
    should_skip = scraper.should_skip_pdp(
        title="Dell Latitude 5490",
        specs={"Condition": "Used - Grade B"},
        url="https://teststore.com/products/dell-latitude-5490",
        description="Used import laptop from Dubai",
    )
    assert should_skip is True
    assert len(scraper.skipped_laptops) == 1
    assert scraper.skipped_laptops[0].stage == "pdp_filter"
    assert "used_or_refurbished" in scraper.skipped_laptops[0].reason


def test_pipeline_gate3_drops_non_laptop_in_process_single():
    pipeline = GenericCatalogPipeline(no_audit=True)

    non_laptop = RetailerProduct(
        store_name="TestStore",
        store_key="test_store",
        store_domain="teststore.com",
        title="ASUS ROG Strix 32-inch 1440P Curved HDR400 Gaming Monitor",
        product_url="https://teststore.com/products/asus-rog-monitor",
        price_egp=15000.0,
        specs={"Screen Size": "32 inch", "Resolution": "2560x1440"},
    )

    result = pipeline.process_single(non_laptop)
    assert result is None


def test_pipeline_gate3_drops_non_laptop_in_process_catalog():
    pipeline = GenericCatalogPipeline(no_audit=True)

    valid_laptop = RetailerProduct(
        store_name="TestStore",
        store_key="test_store",
        store_domain="teststore.com",
        title="ASUS Zenbook 14 OLED UX3405MA Intel Core Ultra 7 155H 16GB 1TB SSD",
        product_url="https://teststore.com/products/asus-zenbook-14",
        price_egp=55000.0,
        specs={"Processor": "Intel Core Ultra 7 155H", "RAM": "16GB", "Storage": "1TB SSD"},
    )

    accessory = RetailerProduct(
        store_name="TestStore",
        store_key="test_store",
        store_domain="teststore.com",
        title="Dell EcoLoop Pro Laptop Backpack 15 inch",
        product_url="https://teststore.com/products/dell-backpack",
        price_egp=1200.0,
        specs={},
    )

    used_laptop = RetailerProduct(
        store_name="TestStore",
        store_key="test_store",
        store_domain="teststore.com",
        title="USED HP Pro x360 Fortis 11 G10 2-in-1 Touch Laptop – Core i5-1230U",
        product_url="https://teststore.com/products/hp-pro-used",
        price_egp=18000.0,
        specs={"Condition": "Refurbished"},
    )

    results = pipeline.process_catalog([valid_laptop, accessory, used_laptop], store_key="test_store")
    # Only the genuine brand new laptop should survive Gate 3
    assert len(results) == 1
    assert results[0]["title"] == valid_laptop.title
    assert results[0]["store_name"] == "TestStore"
    assert results[0]["store_key"] == "test_store"
