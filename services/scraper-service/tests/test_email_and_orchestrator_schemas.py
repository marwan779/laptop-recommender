"""Unit tests for email schemas, templates, email service edge cases, and orchestrator request normalization."""

from datetime import datetime, timedelta
from pathlib import Path
import smtplib
from unittest.mock import MagicMock, patch
import pytest

from app.core.email_config import EmailSettings
from app.email.templates import (
    build_batch_finished_email,
    build_single_finished_email,
)
from app.schemas.email import (
    BatchScrapeReport,
    EmailSendRequest,
    ScraperFinishedReport,
    TargetSummaryItem,
)
from app.schemas.laptop import BrandCatalogResult, LaptopSummary, StoreCatalogResult
from app.schemas.orchestrator import ScrapeRequest, ScrapeResponse, ScrapeTargetResult
from app.services.email_service import EmailService


# =============================================================================
# 1. Orchestrator ScrapeRequest Validators & Normalization
# =============================================================================


def test_scrape_request_normalize_targets_various_inputs():
    """Verify normalize_targets handles None, strings, lists with placeholders, and edge cases."""
    # None -> 'all'
    req_none = ScrapeRequest(target_type="brand", targets=None)
    assert req_none.targets == "all"

    # 'all', empty string, or 'string' placeholder -> 'all'
    assert ScrapeRequest(target_type="brand", targets="all").targets == "all"
    assert ScrapeRequest(target_type="brand", targets="").targets == "all"
    assert ScrapeRequest(target_type="brand", targets="  ").targets == "all"
    assert ScrapeRequest(target_type="brand", targets="string").targets == "all"
    assert ScrapeRequest(target_type="brand", targets="STRING").targets == "all"

    # Single string brand -> ['asus']
    assert ScrapeRequest(target_type="brand", targets="Asus").targets == ["asus"]

    # List with dummy placeholders filtered out
    req_list = ScrapeRequest(
        target_type="brand",
        targets=["asus", "string", "None", "null", "  ", "GIGABYTE"],
    )
    assert req_list.targets == ["asus", "gigabyte"]

    # List of only dummy placeholders -> falls back to 'all'
    req_dummy_list = ScrapeRequest(target_type="brand", targets=["string", "none", " "])
    assert req_dummy_list.targets == "all"


def test_scrape_request_normalize_positive_ints_boundary_cases():
    """Verify normalize_positive_ints converts 0, negative values, and non-ints to None."""
    # None stays None
    assert ScrapeRequest(target_type="brand", max_pages=None).max_pages is None
    assert ScrapeRequest(target_type="brand", limit=None).limit is None

    # Positive integer kept
    assert ScrapeRequest(target_type="brand", max_pages=5).max_pages == 5
    assert ScrapeRequest(target_type="brand", limit=10).limit == 10

    # Boundary 0 and negative integers converted to None
    assert ScrapeRequest(target_type="brand", max_pages=0).max_pages is None
    assert ScrapeRequest(target_type="brand", max_pages=-1).max_pages is None
    assert ScrapeRequest(target_type="brand", limit=0).limit is None
    assert ScrapeRequest(target_type="brand", limit=-5).limit is None

    # String representation of positive int converted
    assert ScrapeRequest(target_type="brand", limit="15").limit == 15

    # Non-convertible string or type converted to None
    assert ScrapeRequest(target_type="brand", limit="invalid_number").limit is None


def test_scrape_request_normalize_until_model_branches():
    """Verify normalize_until_model handles single strings, lists, placeholders, and None."""
    # None
    assert ScrapeRequest(target_type="brand", until_model=None).until_model is None

    # String placeholders converted to None
    assert ScrapeRequest(target_type="brand", until_model="").until_model is None
    assert ScrapeRequest(target_type="brand", until_model="   ").until_model is None
    assert ScrapeRequest(target_type="brand", until_model="string").until_model is None
    assert ScrapeRequest(target_type="brand", until_model="none").until_model is None
    assert ScrapeRequest(target_type="brand", until_model="null").until_model is None

    # Valid string
    assert ScrapeRequest(target_type="brand", until_model="  S5452  ").until_model == "S5452"

    # List of strings with placeholders filtered
    req_list = ScrapeRequest(target_type="brand", until_model=["S5452", "string", "none", "FA506"])
    assert req_list.until_model == ["S5452", "FA506"]

    # List with only placeholders -> None
    assert ScrapeRequest(target_type="brand", until_model=["string", "null"]).until_model is None


def test_scrape_request_normalize_output_dir_branches():
    """Verify normalize_output_dir handles None, empty strings, placeholders, and valid paths."""
    assert ScrapeRequest(target_type="brand", output_dir=None).output_dir is None
    assert ScrapeRequest(target_type="brand", output_dir="").output_dir is None
    assert ScrapeRequest(target_type="brand", output_dir="   ").output_dir is None
    assert ScrapeRequest(target_type="brand", output_dir="string").output_dir is None
    assert ScrapeRequest(target_type="brand", output_dir="none").output_dir is None
    assert ScrapeRequest(target_type="brand", output_dir="null").output_dir is None

    assert ScrapeRequest(target_type="brand", output_dir="  scraping-results  ").output_dir == "scraping-results"


# =============================================================================
# 2. Email Schema: BatchScrapeReport from ScrapeResponse
# =============================================================================


def test_batch_scrape_report_from_scrape_response_all_successful():
    """Verify BatchScrapeReport construction when all targets succeed."""
    start_time = datetime(2026, 10, 1, 10, 0, 0)
    end_time = start_time + timedelta(seconds=12.5)

    brand_cat = BrandCatalogResult(
        brand="ASUS",
        official_catalog_url="https://asus.com",
        scrape_mode="level1",
        total_laptops=5,
        total_skipped=1,
        latest_pointers=["Zenbook 14", "Vivobook 15"],
        laptops=[],
    )

    store_cat = StoreCatalogResult(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        scrape_mode="level1",
        total_products=10,
        total_skipped=2,
        latest_pointers=["Dell G15"],
        products=[],
    )

    response = ScrapeResponse(
        results=[
            ScrapeTargetResult(
                target_type="brand",
                target_key="asus",
                target_name="ASUS",
                level=1,
                items_scraped=5,
                brand_result=brand_cat,
            ),
            ScrapeTargetResult(
                target_type="store",
                target_key="compumarts",
                target_name="Compumarts",
                level=1,
                items_scraped=10,
                store_result=store_cat,
            ),
        ],
        total_targets=2,
        total_items_scraped=15,
        started_at=start_time.isoformat(),
        finished_at=end_time.isoformat(),
    )

    req = ScrapeRequest(target_type="brand", targets="all")
    report = BatchScrapeReport.from_scrape_response(response, req)

    assert report.batch_type == "brand"
    assert report.status == "SUCCESS"
    assert report.total_targets == 2
    assert report.total_scraped == 15
    assert report.total_skipped == 3  # 1 + 2
    assert report.duration_seconds == 12.5
    assert len(report.targets) == 2

    asus_item = report.targets[0]
    assert asus_item.status == "SUCCESS"
    assert asus_item.scraped_count == 5
    assert asus_item.skipped_count == 1
    assert asus_item.latest_pointers == ["Zenbook 14", "Vivobook 15"]

    comp_item = report.targets[1]
    assert comp_item.status == "SUCCESS"
    assert comp_item.scraped_count == 10
    assert comp_item.skipped_count == 2


def test_batch_scrape_report_from_scrape_response_partial_and_total_failure():
    """Verify BatchScrapeReport statuses: PARTIAL_SUCCESS and FAILED."""
    start_time = datetime(2026, 10, 1, 10, 0, 0)

    # 1. Partial success: 1 success, 1 failure
    response_partial = ScrapeResponse(
        results=[
            ScrapeTargetResult(
                target_type="brand",
                target_key="asus",
                target_name="ASUS",
                level=1,
                items_scraped=5,
            ),
            ScrapeTargetResult(
                target_type="brand",
                target_key="lenovo",
                target_name="Lenovo",
                level=1,
                items_scraped=0,
                error="Network timeout",
            ),
        ],
        total_targets=2,
        total_items_scraped=5,
        started_at=start_time.isoformat(),
        finished_at=None,  # Tests finished_at is None fallback
    )
    req = ScrapeRequest(target_type="brand", targets=["asus", "lenovo"])
    report_partial = BatchScrapeReport.from_scrape_response(response_partial, req)
    assert report_partial.status == "PARTIAL_SUCCESS"
    assert report_partial.targets[1].status == "FAILED"
    assert report_partial.targets[1].error_message == "Network timeout"

    # 2. Total failure: all targets fail
    response_failed = ScrapeResponse(
        results=[
            ScrapeTargetResult(
                target_type="brand",
                target_key="asus",
                target_name="ASUS",
                level=1,
                items_scraped=0,
                error="HTTP 503",
            ),
        ],
        total_targets=1,
        total_items_scraped=0,
        started_at="invalid-iso-date",  # Tests datetime parsing exception handling
        finished_at="invalid-iso-date",
    )
    report_failed = BatchScrapeReport.from_scrape_response(response_failed, req)
    assert report_failed.status == "FAILED"
    assert report_failed.duration_seconds == 0.0


# =============================================================================
# 3. Email Templates Tests (Batch and Single finished)
# =============================================================================


def test_build_single_finished_email_with_watermark_and_storage_key():
    """Verify build_single_finished_email renders watermark, storage badge, and plaintext key."""
    report = ScraperFinishedReport(
        target_name="ASUS",
        target_type="brand",
        target_key="asus",
        status="SUCCESS",
        mode="Level 1",
        scraped_count=12,
        skipped_count=0,
        latest_pointers=["Zenbook 14", "TUF A15"],
        duration_seconds=4.2,
        until_model="S5452",
        storage_key="brands/brand_asus.json",
        error_message=None,
        timestamp="2026-10-01 12:00:00 UTC",
    )

    subject, html_body, text_body = build_single_finished_email(report)

    assert "[SUCCESS] ASUS Scrape Report" in subject
    assert "Incremental Watermark Used:" in html_body
    assert "S5452" in html_body  # Watermark rendered in HTML
    assert "brands/brand_asus.json" in html_body  # S3 badge rendered in HTML
    assert "Storage Key (S3): brands/brand_asus.json" in text_body
    assert "Zenbook 14" in text_body


def test_build_batch_finished_email_brand_and_store_templates():
    """Verify build_batch_finished_email renders metrics, table rows, error boxes, and text breakdown."""
    item1 = TargetSummaryItem(
        target_type="brand",
        target_key="asus",
        target_name="ASUS",
        status="SUCCESS",
        mode="Level 1",
        scraped_count=20,
        skipped_count=2,
        latest_pointers=["Zenbook Pro"],
    )
    item2 = TargetSummaryItem(
        target_type="brand",
        target_key="lenovo",
        target_name="Lenovo",
        status="FAILED",
        mode="Level 1",
        scraped_count=0,
        skipped_count=0,
        error_message="Gateway timeout connecting to PSREF",
    )

    batch_report = BatchScrapeReport(
        batch_type="brand",
        status="PARTIAL_SUCCESS",
        total_targets=2,
        total_scraped=20,
        total_skipped=2,
        duration_seconds=15.8,
        started_at="2026-10-01T12:00:00",
        finished_at="2026-10-01T12:00:15",
        targets=[item1, item2],
    )

    subject, html_body, text_body = build_batch_finished_email(batch_report)

    assert "[PARTIAL SUCCESS] Brand Catalogs Scrape Complete" in subject
    assert "20 Ingested, 2 Skipped (15.8s)" in subject

    # HTML assertions
    assert "Brand Catalogs Ingestion Report" in html_body
    assert "ASUS" in html_body
    assert "Lenovo" in html_body
    assert "Gateway timeout connecting to PSREF" in html_body

    # Text assertions
    assert "=== Brand Catalogs Ingestion Report ===" in text_body
    assert "Total Ingested: 20" in text_body
    assert "Total Skipped: 2" in text_body
    assert "• ASUS (Level 1): 20 scraped, 2 skipped [SUCCESS]" in text_body
    assert "• Lenovo (Level 1): 0 scraped, 0 skipped [FAILED]" in text_body
    assert "Error: Gateway timeout connecting to PSREF" in text_body


def test_build_batch_finished_email_store_batch_label():
    """Verify batch_type='store' renders 'Retail Stores' in subject and body."""
    batch_report = BatchScrapeReport(
        batch_type="store",
        status="SUCCESS",
        total_targets=1,
        total_scraped=50,
        total_skipped=0,
        duration_seconds=8.0,
        started_at="2026-10-01T12:00:00",
        finished_at="2026-10-01T12:00:08",
        targets=[
            TargetSummaryItem(
                target_type="store",
                target_key="btech",
                target_name="B.TECH",
                status="SUCCESS",
                mode="Level 2",
                scraped_count=50,
                skipped_count=0,
            )
        ],
    )

    subject, html_body, text_body = build_batch_finished_email(batch_report)
    assert "[SUCCESS] Retail Stores Scrape Complete" in subject
    assert "Retail Stores Ingestion Report" in html_body
    assert "B.TECH" in text_body


# =============================================================================
# 4. EmailService Comprehensive Edge Cases & Error Handling
# =============================================================================


def test_email_service_disabled_notifications():
    """When email_notifications_enabled is False, send_email and send_batch_report return False."""
    settings = EmailSettings(email_notifications_enabled=False)
    service = EmailService(settings=settings)
    assert service.is_enabled is False

    req = EmailSendRequest(
        recipients=["user@example.com"],
        subject="Test",
        html_body="<p>Test</p>",
    )
    assert service.send_email(req) is False

    batch_report = BatchScrapeReport(
        batch_type="brand",
        status="SUCCESS",
        started_at="",
        finished_at="",
    )
    assert service.send_batch_report(batch_report) is False


def test_email_service_unconfigured_falls_back_to_preview_file(tmp_path):
    """When SMTP is not configured, send_email saves preview HTML file and returns True."""
    settings = EmailSettings(
        smtp_user="",
        smtp_password="",
        report_recipients="",
    )
    service = EmailService(settings=settings)
    assert service.settings.is_configured is False

    req = EmailSendRequest(
        recipients=["test@example.com"],
        subject="Preview Test",
        html_body="<h1>Preview Content</h1>",
    )

    with patch.object(service, "_save_preview_html") as mock_save:
        mock_save.return_value = tmp_path / "preview.html"
        assert service.send_email(req) is True
        mock_save.assert_called_once_with(req)


def test_email_service_smtp_send_success_with_tls():
    """Verify SMTP connection, TLS initialization, login, and sendmail call."""
    settings = EmailSettings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="secretpassword",
        smtp_use_tls=True,
        smtp_from_email="noreply@example.com",
        smtp_from_name="Scraper Bot",
        report_recipients="admin@example.com",
    )
    service = EmailService(settings=settings)
    assert service.settings.is_configured is True

    req = EmailSendRequest(
        recipients=["recipient@example.com"],
        subject="Live Alert",
        html_body="<p>Alert Body</p>",
        text_body="Alert Body",
    )

    mock_smtp_instance = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp_instance) as mock_smtp_cls:
        assert service.send_email(req) is True

        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=15)
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once_with("user@example.com", "secretpassword")
        mock_smtp_instance.send_message.assert_called_once()
        mock_smtp_instance.quit.assert_called_once()


def test_email_service_smtp_send_without_tls():
    """Verify SMTP connection without TLS (starttls not called)."""
    settings = EmailSettings(
        smtp_host="smtp.example.com",
        smtp_port=25,
        smtp_user="user@example.com",
        smtp_password="secretpassword",
        smtp_use_tls=False,
        report_recipients="admin@example.com",
    )
    service = EmailService(settings=settings)

    req = EmailSendRequest(
        recipients=["recipient@example.com"],
        subject="No TLS Alert",
        html_body="<p>Body</p>",
    )

    mock_smtp_instance = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp_instance):
        assert service.send_email(req) is True
        mock_smtp_instance.starttls.assert_not_called()
        mock_smtp_instance.login.assert_called_once()


def test_email_service_smtp_auth_error_saves_preview_fallback():
    """Verify SMTPAuthenticationError triggers fallback preview save and returns False."""
    settings = EmailSettings(
        smtp_user="user@example.com",
        smtp_password="wrongpassword",
        report_recipients="admin@example.com",
    )
    service = EmailService(settings=settings)

    req = EmailSendRequest(
        recipients=["recipient@example.com"],
        subject="Failed Alert",
        html_body="<p>Body</p>",
    )

    mock_smtp_instance = MagicMock()
    mock_smtp_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")

    with patch("smtplib.SMTP", return_value=mock_smtp_instance):
        with patch.object(service, "_save_preview_html") as mock_save:
            assert service.send_email(req) is False
            mock_save.assert_called_once_with(req)


def test_email_service_send_batch_report_defaults():
    """Verify send_batch_report builds request and uses settings recipients when none passed."""
    settings = EmailSettings(
        smtp_user="user@example.com",
        smtp_password="password",
        report_recipients="rep1@example.com, rep2@example.com",
    )
    service = EmailService(settings=settings)

    batch_report = BatchScrapeReport(
        batch_type="store",
        status="SUCCESS",
        started_at="2026-10-01T12:00:00",
        finished_at="2026-10-01T12:00:10",
    )

    with patch.object(service, "send_email", return_value=True) as mock_send:
        assert service.send_batch_report(batch_report) is True
        call_arg = mock_send.call_args[0][0]
        assert isinstance(call_arg, EmailSendRequest)
        assert call_arg.recipients == ["rep1@example.com", "rep2@example.com"]
        assert "Retail Stores" in call_arg.subject


def test_email_service_safe_background_send_handles_worker_exception():
    """Verify _safe_background_send catches unexpected exceptions in worker thread."""
    service = EmailService()
    report = ScraperFinishedReport(
        target_name="Faulty Target",
        target_type="brand",
        target_key="faulty",
        status="FAILED",
        mode="Level 1",
    )

    with patch.object(service, "send_scraper_finished_report", side_effect=RuntimeError("Worker thread crash")):
        success = service._safe_background_send(report)
        assert success is False
