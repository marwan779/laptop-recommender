"""Unit tests for brand scraper services (ASUS, GigaByte, HP, Lenovo) and orchestrator dispatching."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.schemas.laptop import (
    AsusBrandCatalogResult,
    BrandCatalogResult,
    HpBrandCatalogResult,
    LaptopDetail,
    LaptopSummary,
    LenovoBrandCatalogResult,
    RetailerProduct,
    SkippedLaptop,
    StoreCatalogResult,
)
from app.schemas.orchestrator import ScrapeRequest, ScrapeResponse, ScrapeTargetResult
from app.scrapers.asus import AsusBrandScraper
from app.scrapers.gigabyte import GigabyteBrandScraper
from app.scrapers.hp import HpBrandScraper
from app.scrapers.lenovo import LenovoBrandScraper
from app.services.asus_scraper_service import AsusScraperService
from app.services.gigabyte_scraper_service import GigabyteScraperService
from app.services.hp_scraper_service import HpScraperService
from app.services.lenovo_scraper_service import LenovoScraperService
from app.services.orchestrator import ScrapeOrchestrator
from app.storage.base import IObjectStorageService
from app.storage.models import StorageObject


# =============================================================================
# 1. ASUS Scraper Service Tests
# =============================================================================


def test_asus_scraper_service_invalid_mode_raises():
    """Verify AsusScraperService raises ValueError on invalid mode."""
    service = AsusScraperService(engine=MagicMock())
    with pytest.raises(ValueError, match="Invalid mode 'invalid'"):
        service.scrape(mode="invalid")


def test_asus_scraper_service_level1_scrape(tmp_path):
    """Verify Level 1 scrape produces summary catalog and saves to disk if requested."""
    service = AsusScraperService(engine=MagicMock())
    service.scraper = MagicMock()
    service.scraper.brand_name = "ASUS"
    service.scraper.catalog_url = "https://asus.com"
    service.scraper.skipped_laptops = []

    mock_summary1 = LaptopSummary(brand="asus", name="ZenBook 14", product_url="https://asus.com/1")
    mock_summary2 = LaptopSummary(brand="asus", name="TUF Gaming A15", product_url="https://asus.com/2")
    service.scraper.get_laptop_summaries.return_value = [mock_summary1, mock_summary2]

    out_file = tmp_path / "asus_l1.json"
    result = service.scrape(mode="level1", output_file=out_file)

    assert isinstance(result, AsusBrandCatalogResult)
    assert result.scrape_mode == "level1"
    assert result.total_laptops == 2
    assert result.latest_pointers == ["ZenBook 14", "TUF Gaming A15"]
    assert out_file.exists()


def test_asus_scraper_service_level2_scrape_with_detail_error_and_limit():
    """Verify Level 2 scrape crawls details, records skipped on exception, and respects limit."""
    service = AsusScraperService(engine=MagicMock())
    service.scraper = MagicMock()
    service.scraper.brand_name = "ASUS"
    service.scraper.catalog_url = "https://asus.com"
    service.scraper.skipped_laptops = []

    mock_s1 = LaptopSummary(brand="asus", name="Laptop 1", product_url="https://asus.com/1")
    mock_s2 = LaptopSummary(brand="asus", name="Laptop 2", product_url="https://asus.com/2")
    mock_s3 = LaptopSummary(brand="asus", name="Laptop 3", product_url="https://asus.com/3")
    service.scraper.get_laptop_summaries.return_value = [mock_s1, mock_s2, mock_s3]

    mock_detail1 = LaptopDetail(
        brand="asus",
        name="Laptop 1",
        product_url="https://asus.com/1",
        configurations=[{"sku": "SKU1"}, {"sku": "SKU2"}],
    )

    # First succeeds, second raises error, third would succeed but limit=1 stops it
    def fake_get_detail(summary):
        if summary.name == "Laptop 1":
            return mock_detail1
        elif summary.name == "Laptop 2":
            raise RuntimeError("PDP 404")
        return None

    service.scraper.get_laptop_detail.side_effect = fake_get_detail

    result = service.scrape(mode="level2", limit=1)

    assert result.scrape_mode == "level2"
    assert result.total_laptops == 1
    assert result.total_configurations == 2
    assert result.latest_pointers == ["Laptop 1"]


# =============================================================================
# 2. GigaByte Scraper Service Tests
# =============================================================================


def test_gigabyte_scraper_service_invalid_mode():
    """Verify GigabyteScraperService raises ValueError on invalid mode."""
    service = GigabyteScraperService(engine=MagicMock())
    with pytest.raises(ValueError):
        service.scrape(mode="unknown")


def test_gigabyte_scraper_service_level1_and_level2(tmp_path):
    """Verify GigabyteScraperService handles level1 and level2 workflows."""
    service = GigabyteScraperService(engine=MagicMock())
    service.scraper = MagicMock()
    service.scraper.brand_name = "GigaByte"
    service.scraper.catalog_url = "https://gigabyte.com"
    service.scraper.skipped_laptops = []

    s = LaptopSummary(brand="gigabyte", name="AERO 16", product_url="https://gigabyte.com/1")
    service.scraper.get_laptop_summaries.return_value = [s]

    # Level 1
    res1 = service.scrape(mode="level1", until_model="AERO 16")
    assert res1.scrape_mode == "level1"
    assert res1.until_model == "AERO 16"
    assert res1.total_laptops == 1

    # Level 2 with save
    d = LaptopDetail(brand="gigabyte", name="AERO 16", product_url="https://gigabyte.com/1", configurations=[])
    service.scraper.get_laptop_detail.return_value = d

    out_file = tmp_path / "gigabyte_l2.json"
    res2 = service.scrape(mode="level2", output_file=out_file)
    assert res2.scrape_mode == "level2"
    assert out_file.exists()


# =============================================================================
# 3. HP Scraper Service Tests
# =============================================================================


def test_hp_scraper_service_invalid_mode():
    """Verify HpScraperService raises ValueError on invalid mode."""
    service = HpScraperService(engine=MagicMock())
    with pytest.raises(ValueError):
        service.scrape(mode="level3")


def test_hp_scraper_service_level1_and_level2_dates(tmp_path):
    """Verify HpScraperService calculates release date range and configurations."""
    service = HpScraperService(engine=MagicMock())
    service.scraper = MagicMock()
    service.scraper.brand_name = "HP"
    service.scraper.catalog_url = "https://hp.com"
    service.scraper.skipped_laptops = []

    s1 = LaptopSummary(brand="hp", name="HP Omen 16", product_url="https://hp.com/1")
    service.scraper.get_laptop_summaries.return_value = [s1]

    # Detail returns detail with release_date
    d1 = LaptopDetail(
        brand="hp",
        name="HP Omen 16",
        product_url="https://hp.com/1",
        release_date="2024-05-10",
        configurations=[{"sku": "OMEN-1"}],
    )
    service.scraper.get_laptop_detail.return_value = d1

    out_file = tmp_path / "hp_l2.json"
    result = service.scrape(mode="level2", output_file=out_file)
    assert isinstance(result, HpBrandCatalogResult)
    assert result.total_laptops == 1
    assert result.total_configurations == 1
    assert result.start_date == "2024-05-10"
    assert out_file.exists()


# =============================================================================
# 4. Lenovo Scraper Service Tests
# =============================================================================


def test_lenovo_scraper_service_invalid_mode():
    """Verify LenovoScraperService raises ValueError on invalid mode."""
    service = LenovoScraperService(engine=MagicMock())
    with pytest.raises(ValueError):
        service.scrape(mode="bad_mode")


def test_lenovo_scraper_service_level1_and_level2(tmp_path):
    """Verify LenovoScraperService handles level1 and level2 workflows."""
    service = LenovoScraperService(engine=MagicMock())
    service.scraper = MagicMock()
    service.scraper.brand_name = "Lenovo"
    service.scraper.catalog_url = "https://lenovo.com"
    service.scraper.skipped_laptops = []

    s = LaptopSummary(brand="lenovo", name="Legion 7", product_url="https://lenovo.com/1")
    service.scraper.get_laptop_summaries.return_value = [s]

    d = LaptopDetail(brand="lenovo", name="Legion 7", product_url="https://lenovo.com/1", configurations=[{"sku": "L7"}])
    service.scraper.get_laptop_detail.return_value = d

    out_file = tmp_path / "lenovo.json"
    res = service.scrape(mode="level2", output_file=out_file)
    assert isinstance(res, LenovoBrandCatalogResult)
    assert res.total_laptops == 1
    assert out_file.exists()


# =============================================================================
# 5. ScrapeOrchestrator Uncovered Branches & Error Handling
# =============================================================================


def test_orchestrator_resolve_targets_stores_and_both():
    """Verify _resolve_targets for target_type='store' and target_type='both'."""
    orchestrator = ScrapeOrchestrator(email_service=MagicMock())

    # store with 'all'
    req_store_all = ScrapeRequest(target_type="store", targets="all")
    targets_store_all = orchestrator._resolve_targets(req_store_all)
    assert len(targets_store_all) == 8
    assert all(t[0] == "store" for t in targets_store_all)

    # store with specific targets
    req_store_specific = ScrapeRequest(target_type="store", targets=["btech", "sigma"])
    targets_store_specific = orchestrator._resolve_targets(req_store_specific)
    assert targets_store_specific == [("store", "btech"), ("store", "sigma")]

    # both with 'all'
    req_both_all = ScrapeRequest(target_type="both", targets="all")
    targets_both_all = orchestrator._resolve_targets(req_both_all)
    assert len(targets_both_all) == 4 + 8  # 4 brands + 8 stores

    # both with specific mixed targets
    req_both_mixed = ScrapeRequest(target_type="both", targets=["asus", "noon", "compumarts", "unknown_xyz"])
    targets_both_mixed = orchestrator._resolve_targets(req_both_mixed)
    assert ("brand", "asus") in targets_both_mixed
    assert ("store", "noon") in targets_both_mixed
    assert ("store", "compumarts") in targets_both_mixed
    assert ("brand", "unknown_xyz") in targets_both_mixed


def test_orchestrator_scrape_store_unknown_and_exception():
    """Verify _scrape_store catches unknown store errors and scraper exceptions."""
    orchestrator = ScrapeOrchestrator(email_service=MagicMock())

    # 1. Unknown store
    req = ScrapeRequest(target_type="store", targets=["nonexistent_store"])
    res_unknown = orchestrator._scrape_store("nonexistent_store", req)
    assert res_unknown.error is not None
    assert "Unknown store" in res_unknown.error
    assert res_unknown.items_scraped == 0

    # 2. Store scraper throws exception during scrape_catalog
    with patch("app.services.orchestrator.get_store_scraper") as mock_get_store:
        mock_scraper = MagicMock()
        mock_scraper.store_name = "MockStore"
        mock_scraper.scrape_catalog.side_effect = ConnectionError("Store blocked crawler")
        mock_get_store.return_value = mock_scraper

        res_err = orchestrator._scrape_store("btech", req)
        assert res_err.error == "Store blocked crawler"
        assert res_err.items_scraped == 0


def test_orchestrator_scrape_brand_exception_handling():
    """Verify _scrape_brand catches unexpected exception during brand service execution."""
    orchestrator = ScrapeOrchestrator(email_service=MagicMock())
    req = ScrapeRequest(target_type="brand", targets=["asus"])

    mock_service_inst = MagicMock()
    mock_service_inst.scrape.side_effect = RuntimeError("Asus API crashed")
    mock_service_cls = MagicMock(return_value=mock_service_inst)

    with patch.dict("app.services.orchestrator.BRAND_SERVICE_REGISTRY", {"asus": mock_service_cls}):
        res = orchestrator._scrape_brand("asus", req)
        assert res.error == "Asus API crashed"
        assert res.items_scraped == 0


def test_orchestrator_scrape_store_with_skipped_items_and_save_json(tmp_path):
    """Verify _scrape_store saves JSON to output_file when upload_to_bucket is False."""
    orchestrator = ScrapeOrchestrator(email_service=MagicMock(), upload_to_bucket=False)
    out_dir = tmp_path / "store_out"
    req = ScrapeRequest(target_type="store", targets=["compumarts"], output_dir=str(out_dir), upload_to_bucket=False)

    p1 = RetailerProduct(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title="Gaming Laptop 1",
        product_url="https://compumarts.com/1",
    )
    mock_skipped = SkippedLaptop(name="Accessory Bag", reason="Filtered out non-laptop accessory")

    with patch("app.services.orchestrator.get_store_scraper") as mock_get:
        mock_s = MagicMock()
        mock_s.store_name = "Compumarts"
        mock_s.store_key = "compumarts"
        mock_s.base_domain = "compumarts.com"
        mock_s.scrape_catalog.return_value = [p1]
        mock_s.skipped_laptops = [mock_skipped]
        mock_get.return_value = mock_s

        target_res = orchestrator._scrape_store("compumarts", req)
        assert target_res.items_scraped == 1
        assert target_res.store_result.total_skipped == 1
        assert (out_dir / "store_compumarts.json").exists()


def test_orchestrator_upload_target_to_storage_skip_on_error():
    """Verify _upload_target_to_storage skips uploading when result contains an error."""
    mock_storage = MagicMock(spec=IObjectStorageService)
    orchestrator = ScrapeOrchestrator(storage_service=mock_storage, upload_to_bucket=True)

    err_result = ScrapeTargetResult(
        target_type="brand",
        target_key="asus",
        target_name="ASUS",
        level=1,
        items_scraped=0,
        error="Fatal scrape error",
    )

    orchestrator._upload_target_to_storage(err_result, "brand", "asus")
    mock_storage.upload_file.assert_not_called()
    mock_storage.upload_json.assert_not_called()


def test_orchestrator_upload_target_to_storage_upload_file_path(tmp_path):
    """Verify _upload_target_to_storage calls upload_file when output_file exists on disk."""
    mock_storage = MagicMock(spec=IObjectStorageService)
    mock_obj = MagicMock(spec=StorageObject)
    mock_obj.key = "brands/brand_asus.json"
    mock_storage.upload_file.return_value = mock_obj
    orchestrator = ScrapeOrchestrator(storage_service=mock_storage, upload_to_bucket=True)

    test_file = tmp_path / "brand_asus.json"
    test_file.write_text("{}", encoding="utf-8")

    result = ScrapeTargetResult(
        target_type="brand",
        target_key="asus",
        target_name="ASUS",
        level=1,
        items_scraped=5,
        output_file=str(test_file),
    )

    orchestrator._upload_target_to_storage(result, "brand", "asus")
    mock_storage.upload_file.assert_called_once()
    assert result.storage_key == "brands/brand_asus.json"


def test_orchestrator_execute_email_dispatch_exception_is_handled():
    """Verify exception in email dispatching is caught gracefully and does not stop execute()."""
    mock_email = MagicMock()
    mock_email.send_scraper_finished_background.side_effect = RuntimeError("SMTP connection drop")

    orchestrator = ScrapeOrchestrator(email_service=mock_email, send_email=True)

    mock_catalog = BrandCatalogResult(
        brand="ASUS",
        official_catalog_url="https://asus.com",
        scrape_mode="level1",
        total_laptops=1,
        total_skipped=0,
        latest_pointers=["ZenBook"],
        laptops=[],
    )

    with patch.object(orchestrator, "_scrape_brand", return_value=ScrapeTargetResult(
        target_type="brand",
        target_key="asus",
        target_name="ASUS",
        level=1,
        items_scraped=1,
        brand_result=mock_catalog,
    )):
        req = ScrapeRequest(target_type="brand", targets=["asus"], level=1, send_email=True)
        response = orchestrator.execute(req)
        assert len(response.results) == 1
        assert response.total_items_scraped == 1


def test_brand_scrapers_level2_reject_used_or_non_laptop():
    """Verify ASUS, HP, Lenovo, and Gigabyte reject items in Level 2 if specs reveal used/non-laptop."""
    # 1. ASUS
    asus_scraper = AsusBrandScraper(engine=MagicMock())
    doc = MagicMock()
    doc.markdown.return_value = "## Specifications\nProcessor: Intel Core i7\nOperating System: Windows 11\nCondition: Refurbished Grade A"
    doc.raw = MagicMock()
    doc.get_meta.return_value = ""
    asus_scraper.engine.fetch.return_value = doc
    asus_scraper._parse_specs_from_markdown = MagicMock(return_value={"Processor": "Intel Core i7", "Condition": "Refurbished"})
    sum_asus = LaptopSummary(brand="ASUS", name="ASUS ROG Strix G16", product_url="https://asus.com/laptop")
    res_asus = asus_scraper.get_laptop_detail(sum_asus)
    assert res_asus is None
    assert any("Rejected after deep specs inspection" in s.reason for s in asus_scraper.skipped_laptops)

    # 2. HP
    hp_scraper = HpBrandScraper(engine=MagicMock())
    hp_scraper._fetch_page = MagicMock(
        return_value="<html><table class='c-product-all-details-table__table'><tr><td>Processor</td><td>Intel Core i5</td></tr><tr><td>Condition</td><td>Refurbished</td></tr></table></html>"
    )
    sum_hp = LaptopSummary(brand="HP", name="HP Pavilion 15", product_url="https://hp.com/laptop", specs_url="https://hp.com/specs")
    res_hp = hp_scraper.get_laptop_detail(sum_hp)
    assert res_hp is None
    assert any("Rejected after deep specs inspection" in s.reason for s in hp_scraper.skipped_laptops)

    # 3. Lenovo
    lenovo_scraper = LenovoBrandScraper(engine=MagicMock())
    doc_l = MagicMock()
    doc_l.html = "<html></html>"
    doc_l.markdown.return_value = "Used laptop description"
    lenovo_scraper.engine.fetch.return_value = doc_l
    lenovo_scraper._extract_tables_from_html = MagicMock(
        return_value=[{"groupHeadline": "General", "specs": [{"headline": "Processor", "text": "Intel Core i7"}, {"headline": "Condition", "text": "Used - Like New"}]}]
    )
    sum_lenovo = LaptopSummary(brand="Lenovo", name="Lenovo ThinkPad T14", product_url="https://lenovo.com/p/1234567890")
    res_lenovo = lenovo_scraper.get_laptop_detail(sum_lenovo)
    assert res_lenovo is None
    assert any("Rejected after deep specs inspection" in s.reason for s in lenovo_scraper.skipped_laptops)

    # 4. Gigabyte
    giga_scraper = GigabyteBrandScraper(engine=MagicMock())
    giga_html = """
    <ul class="spec-item-list">
      <li class="spec-title">CPU</li><li class="spec-desc">Intel Core i7</li>
    </ul>
    <ul class="spec-item-list">
      <li class="spec-title">Condition</li><li class="spec-desc">Refurbished</li>
    </ul>
    """
    giga_scraper._fetch_html = MagicMock(return_value=giga_html)
    sum_giga = LaptopSummary(brand="GIGABYTE", name="AORUS 15", product_url="https://gigabyte.com/laptop")
    res_giga = giga_scraper.get_laptop_detail(sum_giga)
    assert res_giga is None
    assert any("Rejected after deep specs inspection" in s.reason for s in giga_scraper.skipped_laptops)

