from unittest.mock import MagicMock
import pytest

from app.schemas.laptop import LaptopSummary
from app.scrapers.gigabyte import GigabyteBrandScraper, GigabyteDateExtractor


MOCK_CATALOG_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="gbt-cl-card">
  <div class="gbt-cl-card-top-box">
    <a href="/Laptop/GIGABYTE-EAGLE-GL6J">
      <img src="https://static.gigabyte.com/Product/48746" alt="GL6J" />
    </a>
  </div>
  <div class="gbt-cl-card-top-title">GIGABYTE EAGLE GL6J</div>
  <div class="gbt-cl-card-badge">NEW</div>
  <div class="gbt-cl-card-bt-tags">
    <span>16" 16:10 WQXGA 165Hz Display</span>
    <span>Intel® Core™ Ultra processor (Series 2)</span>
    <span>NVIDIA® GeForce RTX™ 50 Series Laptop GPU</span>
  </div>
</div>

<div class="gbt-cl-card">
  <div class="gbt-cl-card-top-box">
    <a href="/Laptop/AORUS-16X--2024">
      <img src="https://static.gigabyte.com/Product/48726" alt="16X" />
    </a>
  </div>
  <div class="gbt-cl-card-top-title">AORUS 16X (2024)</div>
  <div class="gbt-cl-card-bt-tags">
    <span>16" 16:10 WQXGA 165Hz Display</span>
    <span>14th Gen Intel® Core™ i9-14900HX</span>
    <span>NVIDIA® GeForce RTX™ 4070 Laptop GPU</span>
  </div>
</div>
</body>
</html>
"""

MOCK_SPEC_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="spec-content">
  <ul class="spec-item-list">
    <li class="spec-title"><div>OS</div></li>
    <li class="spec-desc"><div>Windows 11 Home</div></li>
  </ul>
  <ul class="spec-item-list">
    <li class="spec-title"><div>CPU</div></li>
    <li class="spec-desc"><div>14th Gen Intel® Core™ i9-14900HX Processor</div></li>
  </ul>
  <ul class="spec-item-list">
    <li class="spec-title"><div>Video Graphics</div></li>
    <li class="spec-desc"><div>NVIDIA® GeForce RTX™ 4070 Laptop GPU 8GB GDDR6</div></li>
  </ul>
  <ul class="spec-item-list">
    <li class="spec-title"><div>Display</div></li>
    <li class="spec-desc"><div>16.0" 16:10 WQXGA (2560x1600) 165Hz Display</div></li>
  </ul>
  <ul class="spec-item-list">
    <li class="spec-title"><div>System Memory</div></li>
    <li class="spec-desc"><div>2x DDR5 Slots (DDR5-5600MHz, Up to 64GB)</div></li>
  </ul>
  <ul class="spec-item-list">
    <li class="spec-title"><div>Storage</div></li>
    <li class="spec-desc"><div>2x M.2 SSD slots (PCIe® Gen4x4 NVMe™ M.2 SSD)</div></li>
  </ul>
  <ul class="spec-item-list">
    <li class="spec-title"><div>Battery</div></li>
    <li class="spec-desc"><div>Li Polymer 99Wh</div></li>
  </ul>
  <ul class="spec-item-list">
    <li class="spec-title"><div>Weight</div></li>
    <li class="spec-desc"><div>~2.3 kg</div></li>
  </ul>
  <ul class="spec-item-list">
    <li class="spec-title"><div>Color</div></li>
    <li class="spec-desc"><div>Midnight Gray</div></li>
  </ul>
</div>
</body>
</html>
"""


def test_gigabyte_properties():
    scraper = GigabyteBrandScraper()
    assert scraper.brand_name == "GigaByte"
    assert "gigabyte.com" in scraper.catalog_url


def test_gigabyte_family_and_model():
    scraper = GigabyteBrandScraper()
    # Families
    assert scraper._determine_family("AORUS MASTER 16 AM6H", "/Laptop/AORUS-MASTER-16-AM6H") == "AORUS"
    assert scraper._determine_family("GIGABYTE AERO X16 EG64H", "/Laptop/GIGABYTE-AERO-X16-EG64H") == "AERO"
    assert scraper._determine_family("GIGABYTE EAGLE GL6J", "/Laptop/GIGABYTE-EAGLE-GL6J") == "GIGABYTE EAGLE"
    assert scraper._determine_family("GIGABYTE GAMING A16 GA6EH", "/Laptop/GIGABYTE-GAMING-A16-GA6EH") == "GIGABYTE Gaming"
    assert scraper._determine_family("G6X (2024)", "/Laptop/G6X--2024") == "GIGABYTE Gaming"

    # Model codes
    assert scraper._extract_model_code("GIGABYTE EAGLE GL6J", "/Laptop/GIGABYTE-EAGLE-GL6J") == "GL6J"
    assert scraper._extract_model_code("GIGABYTE GAMING A16 GA6EH", "/Laptop/GIGABYTE-GAMING-A16-GA6EH") == "GA6EH"
    assert scraper._extract_model_code("AORUS 16X (2024)", "/Laptop/AORUS-16X--2024") == "16X"


def test_gigabyte_date_extractor():
    # Year in title
    yr, dt = GigabyteDateExtractor.extract_year_and_date("AORUS 16X (2024)")
    assert yr == 2024
    assert dt == "2024-01-01"

    # RTX 50 hardware pattern
    yr, dt = GigabyteDateExtractor.extract_year_and_date("GIGABYTE EAGLE GL6J", "NVIDIA RTX 5070 Series 2")
    assert yr == 2025

    # 13th Gen hardware pattern
    yr, dt = GigabyteDateExtractor.extract_year_and_date("AORUS 15", "13th Gen Intel Core i7-13700H")
    assert yr == 2023


def test_gigabyte_watermark_matching():
    scraper = GigabyteBrandScraper()
    assert scraper._matches_watermark("AORUS 16X (2024)", "16X") is True
    assert scraper._matches_watermark("GIGABYTE EAGLE GL6J", "GL6J") is True
    assert scraper._matches_watermark("aorus-16x-2024", "16X") is True
    assert scraper._matches_watermark("GIGABYTE GAMING A16", "GL6J") is False


def test_gigabyte_level1_parse_mock():
    scraper = GigabyteBrandScraper()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_CATALOG_HTML

    scraper._session.get = MagicMock(side_effect=[mock_resp, MagicMock(status_code=200, text="<html></html>")])

    summaries = scraper.get_laptop_summaries(limit=None, max_pages=1)
    assert len(summaries) == 2

    s1 = summaries[0]
    assert s1.brand == "GigaByte"
    assert s1.name == "GIGABYTE EAGLE GL6J"
    assert s1.model == "GL6J"
    assert s1.family == "GIGABYTE EAGLE"
    assert s1.product_url == "https://www.gigabyte.com/Laptop/GIGABYTE-EAGLE-GL6J"
    assert s1.specs_url == "https://www.gigabyte.com/Laptop/GIGABYTE-EAGLE-GL6J/sp#sp"

    s2 = summaries[1]
    assert s2.name == "AORUS 16X (2024)"
    assert s2.family == "AORUS"
    assert s2.release_year == 2024


def test_gigabyte_watermark_stopping_mock():
    scraper = GigabyteBrandScraper()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_CATALOG_HTML

    scraper._session.get = MagicMock(return_value=mock_resp)

    # Setting watermark to second laptop should stop and return only the first laptop
    summaries = scraper.get_laptop_summaries(until_model="16X", max_pages=1)
    assert len(summaries) == 1
    assert summaries[0].name == "GIGABYTE EAGLE GL6J"


def test_gigabyte_level2_specs_mock():
    scraper = GigabyteBrandScraper()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_SPEC_HTML

    scraper._session.get = MagicMock(return_value=mock_resp)

    summary = LaptopSummary(
        brand="GigaByte",
        name="AORUS 16X (2024)",
        family="AORUS",
        model="16X",
        product_url="https://www.gigabyte.com/Laptop/AORUS-16X--2024",
        specs_url="https://www.gigabyte.com/Laptop/AORUS-16X--2024/sp#sp",
    )

    detail = scraper.get_laptop_detail(summary)
    assert detail is not None
    assert detail.name == "AORUS 16X (2024)"
    assert detail.structured_specs["processor"] == "14th Gen Intel® Core™ i9-14900HX Processor"
    assert "RTX™ 4070" in detail.structured_specs["graphics"]
    assert "16.0" in detail.structured_specs["display"]
    assert "99Wh" in detail.structured_specs["battery"]
    assert detail.structured_specs["weight"] == "~2.3 kg"
    assert "Midnight Gray" in detail.colors
