import json
import pytest
from bs4 import BeautifulSoup

from app.stores.noon import NoonStoreScraper
from app.schemas.laptop import RetailerProduct


def test_noon_properties():
    scraper = NoonStoreScraper()
    assert scraper.store_name == "Noon"
    assert scraper.store_key == "noon"
    assert scraper.base_url == "https://www.noon.com"
    assert scraper.base_domain == "noon.com"


def test_noon_parse_price():
    scraper = NoonStoreScraper()
    val, formatted = scraper.parse_egp_price("EGP 29,999.00")
    assert val == 29999.0
    assert formatted == "29,999.00 EGP"

    val2, formatted2 = scraper.parse_egp_price("42,000.00 EGP")
    assert val2 == 42000.0
    assert formatted2 == "42,000.00 EGP"


def test_noon_accessory_filtering():
    scraper = NoonStoreScraper()
    for title in [
        "Noon East Laptop Sleeve Case Cover 15.6 Inch",
        "Anker 65W Fast Wall Charger USB-C Power Adapter",
        "Wireless Optical Gaming Mouse 2.4GHz",
        "Aluminum Laptop Stand Ergonomic Riser",
    ]:
        assert scraper._is_standalone_accessory(title) is True

    for laptop in [
        "Lenovo V15 G3 IAP Laptop Intel Core i5-1235U 8GB RAM 512GB SSD 15.6 FHD",
        "HP 250 G9 Laptop Intel Core i7-1255U 16GB RAM 512GB SSD Iris Xe",
        "Dell Vostro 3520 Laptop Intel Core i3-1215U 8GB RAM 256GB SSD",
    ]:
        assert scraper._is_standalone_accessory(laptop) is False


def test_noon_watermark_matching():
    scraper = NoonStoreScraper()
    assert scraper._matches_watermark("Lenovo V15 G3 N53381483A", "N53381483A") is True
    assert scraper._matches_watermark("HP 250 G9 83DV009GED", "83DV009GED") is True
    assert scraper._matches_watermark("Dell Vostro", "N53381483A") is False


def test_noon_next_data_parsing():
    scraper = NoonStoreScraper()
    next_data_json = {
        "props": {
            "pageProps": {
                "catalog": {
                    "hits": [
                        {
                            "name": "Lenovo V15 G3 IAP Laptop Intel Core i5-1235U 8GB RAM 512GB SSD",
                            "sku": "N53381483A",
                            "price": 21999.00,
                            "url": "/egypt-en/lenovo-v15-g3-iap-laptop/N53381483A/p/",
                            "is_out_of_stock": False,
                            "image_key": "v1680000000/N53381483A_1",
                            "model_number": "82TT00EDED",
                        },
                        {
                            "name": "Noon East Laptop Sleeve Bag 15.6 Inch - Black",
                            "sku": "N50000000A",
                            "price": 499.00,
                            "url": "/egypt-en/laptop-sleeve/N50000000A/p/",
                            "is_out_of_stock": False,
                        },
                    ]
                }
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data_json)}</script></body></html>'

    items = scraper._parse_next_data_hits(html)
    assert len(items) == 2
    assert items[0]["title"] == "Lenovo V15 G3 IAP Laptop Intel Core i5-1235U 8GB RAM 512GB SSD"
    assert items[0]["sku"] == "N53381483A"
    assert items[0]["price_val"] == 21999.0
    assert items[0]["mpn"] == "82TT00EDED"


def test_noon_mock_pdp_specs(monkeypatch):
    scraper = NoonStoreScraper()
    next_pdp_json = {
        "props": {
            "pageProps": {
                "product": {
                    "name": "HP 250 G9 Laptop",
                    "sku": "N53399999A",
                    "model_number": "6F2C1EA",
                    "model_name": "250 G9",
                    "price": 27499.00,
                    "is_out_of_stock": False,
                    "description": "Powerful HP Laptop for office work",
                    "specifications": [
                        {"name": "Processor", "value": "Intel Core i7-1255U"},
                        {"name": "RAM", "value": "16 GB"},
                        {"name": "Storage", "value": "512 GB SSD"},
                        {"name": "Display Size", "value": "15.6 inch"},
                        {"name": "Operating System", "value": "FreeDOS"},
                    ],
                }
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_pdp_json)}</script></body></html>'
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: html)

    specs, raw_desc, mpn, model_code, p_val, p_str, in_stock = scraper._extract_product_specs(
        "https://www.noon.com/egypt-en/hp-250-g9-laptop/N53399999A/p/"
    )

    assert mpn == "6F2C1EA"
    assert model_code == "250 G9"
    assert p_val == 27499.0
    assert in_stock is True
    assert specs.get("Processor") == "Intel Core i7-1255U"
    assert specs.get("RAM") == "16 GB"
    assert specs.get("Operating System") == "FreeDOS"


def test_noon_catalog_watermark_stop(monkeypatch):
    scraper = NoonStoreScraper()
    next_data_json = {
        "props": {
            "pageProps": {
                "catalog": {
                    "hits": [
                        {
                            "name": "Apple MacBook Air 13-inch M3 Chip 16GB 256GB SSD Newest",
                            "sku": "N60000001A",
                            "price": 54000.00,
                            "url": "/egypt-en/macbook-air-m3/N60000001A/p/",
                            "is_out_of_stock": False,
                        },
                        {
                            "name": "Lenovo Legion Slim 5 Watermark Target N60000002A Laptop",
                            "sku": "N60000002A",
                            "price": 62000.00,
                            "url": "/egypt-en/legion-slim-5/N60000002A/p/",
                            "is_out_of_stock": False,
                        },
                        {
                            "name": "Dell Inspiron 3520 Older Laptop",
                            "sku": "N60000003A",
                            "price": 17500.00,
                            "url": "/egypt-en/inspiron-3520/N60000003A/p/",
                            "is_out_of_stock": False,
                        },
                    ]
                }
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data_json)}</script></body></html>'
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: html)

    products = scraper.scrape_catalog(level=1, until_model="N60000002A", max_pages=1)
    assert len(products) == 1
    assert products[0].retailer_sku == "N60000001A"
    assert products[0].price_egp == 54000.0


def test_noon_search_candidates(monkeypatch):
    scraper = NoonStoreScraper()
    next_data_json = {
        "props": {
            "pageProps": {
                "catalog": {
                    "hits": [
                        {
                            "name": "Dell Vostro 3520 Laptop Intel Core i5 8GB 512GB SSD",
                            "sku": "N70000001A",
                            "price": 23500.00,
                            "url": "/egypt-en/vostro-3520/N70000001A/p/",
                            "is_out_of_stock": False,
                        },
                    ]
                }
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data_json)}</script></body></html>'
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: html)
    monkeypatch.setattr(
        scraper,
        "_extract_product_specs",
        lambda url: (
            {"Processor": "Intel Core i5-1235U", "Model Number": "V3520-E0001-ENG"},
            "Dell Vostro Laptop",
            "V3520-E0001-ENG",
            "Vostro 3520",
            23500.0,
            "23,500.00 EGP",
            True,
        ),
    )

    candidates = scraper.search_candidates("Vostro", limit=5)
    assert len(candidates) == 1
    assert "Dell Vostro" in candidates[0].title
    assert candidates[0].retailer_sku == "N70000001A"
    assert candidates[0].price_egp == 23500.0
    assert candidates[0].mpn == "V3520-E0001-ENG"
