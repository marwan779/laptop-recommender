"""Unit tests for the Email Service, templates, background job dispatcher, and orchestrator triggers."""

from concurrent.futures import Future
from pathlib import Path
import threading
from unittest.mock import MagicMock, patch

import pytest

from app.core.email_config import EmailSettings
from app.email.templates import build_batch_finished_email, build_single_finished_email
from app.schemas.email import (
    BatchScrapeReport,
    EmailSendRequest,
    ScraperFinishedReport,
)
from app.schemas.laptop import BrandCatalogResult, LaptopSummary
from app.schemas.orchestrator import ScrapeRequest, ScrapeTargetResult
from app.services.email_service import EmailService
from app.services.orchestrator import ScrapeOrchestrator


# ---------------------------------------------------------------------------
# 1. EmailSettings Tests
# ---------------------------------------------------------------------------

def test_email_settings_parsed_recipients():
    """Verify comma-separated recipients are correctly split into clean list."""
    settings = EmailSettings(
        report_recipients="user1@example.com, user2@example.com ,user3@example.com",
        smtp_user="sender@gmail.com",
        smtp_password="app_password",
    )
    assert settings.parsed_recipients == [
        "user1@example.com",
        "user2@example.com",
        "user3@example.com",
    ]
    assert settings.is_configured is True


def test_email_settings_unconfigured_when_no_credentials():
    """Verify is_configured is False when credentials or recipients are missing."""
    settings = EmailSettings(
        smtp_user="",
        smtp_password="",
        report_recipients="user@example.com",
    )
    assert settings.is_configured is False


def test_email_settings_unconfigured_when_preview_mode():
    """Verify is_configured is False when email_preview_mode is True."""
    settings = EmailSettings(
        smtp_user="user@gmail.com",
        smtp_password="password",
        report_recipients="user@example.com",
        email_preview_mode=True,
    )
    assert settings.is_configured is False


# ---------------------------------------------------------------------------
# 2. DTO & Report Model Tests
# ---------------------------------------------------------------------------

def test_scraper_finished_report_from_brand_result():
    """Verify report construction from successful BrandCatalogResult."""
    brand_catalog = BrandCatalogResult(
        brand="ASUS",
        official_catalog_url="https://asus.com/laptops",
        scrape_mode="level1",
        total_laptops=25,
        total_skipped=2,
        latest_pointers=["Zenbook 14", "ROG Strix G16", "TUF Gaming A15", "Vivobook 15"],
        laptops=[
            LaptopSummary(brand="ASUS", name="Zenbook 14", product_url="https://asus.com/1"),
        ],
    )
    target_result = ScrapeTargetResult(
        target_type="brand",
        target_key="asus",
        target_name="ASUS",
        level=1,
        items_scraped=25,
        brand_result=brand_catalog,
    )

    report = ScraperFinishedReport.from_target_result(
        target_result,
        duration_seconds=12.4,
        until_model="Zenbook 14",
    )

    assert report.target_name == "ASUS"
    assert report.status == "SUCCESS"
    assert report.scraped_count == 25
    assert report.skipped_count == 2
    assert len(report.latest_pointers) == 3  # Capped at top 3
    assert report.latest_pointers[0] == "Zenbook 14"
    assert report.duration_seconds == 12.4
    assert report.until_model == "Zenbook 14"


def test_scraper_finished_report_from_failed_target():
    """Verify report construction when target has an error."""
    target_result = ScrapeTargetResult(
        target_type="store",
        target_key="compumarts",
        target_name="Compumarts",
        level=2,
        items_scraped=0,
        error="Connection refused: 503 Service Unavailable",
    )

    report = ScraperFinishedReport.from_target_result(
        target_result,
        duration_seconds=3.5,
    )

    assert report.target_name == "Compumarts"
    assert report.status == "FAILED"
    assert report.scraped_count == 0
    assert report.skipped_count == 0
    assert report.error_message == "Connection refused: 503 Service Unavailable"


# ---------------------------------------------------------------------------
# 3. HTML/Text Template Builder Tests
# ---------------------------------------------------------------------------

def test_build_single_finished_email_success():
    """Verify subject, HTML body, and plaintext content for a success report."""
    report = ScraperFinishedReport(
        target_type="brand",
        target_key="asus",
        target_name="ASUS",
        status="SUCCESS",
        mode="Level 1",
        scraped_count=100,
        skipped_count=5,
        latest_pointers=["Zenbook 14", "ROG Zephyrus G14", "Vivobook 16"],
        duration_seconds=15.8,
    )

    subject, html_body, text_body = build_single_finished_email(report)

    # Subject line check
    assert "[SUCCESS] ASUS Scrape Report" in subject
    assert "100 Scraped, 5 Skipped" in subject
    assert "15.8s" in subject

    # HTML body check
    assert "Total Scraped" in html_body
    assert "100" in html_body
    assert "Total Skipped" in html_body
    assert "5" in html_body
    assert "Zenbook 14" in html_body
    assert "ROG Zephyrus G14" in html_body
    assert "SUCCESS" in html_body

    # Plain text check
    assert "=== ASUS Scraping Summary ===" in text_body
    assert "Total Scraped: 100" in text_body
    assert "Total Skipped: 5" in text_body


def test_build_single_finished_email_failed():
    """Verify error notice rendering for failed scrape reports."""
    report = ScraperFinishedReport(
        target_type="store",
        target_key="sigma",
        target_name="Sigma Computer",
        status="FAILED",
        mode="Level 2",
        scraped_count=0,
        skipped_count=0,
        duration_seconds=2.1,
        error_message="HTTP 504 Gateway Timeout",
    )

    subject, html_body, text_body = build_single_finished_email(report)

    assert "[FAILED] Sigma Computer Scrape Failed" in subject
    assert "HTTP 504 Gateway Timeout" in html_body
    assert "EXECUTION ERROR" in html_body.upper()
    assert "HTTP 504 Gateway Timeout" in text_body


# ---------------------------------------------------------------------------
# 4. EmailService & Background Job Tests
# ---------------------------------------------------------------------------

def test_email_service_preview_fallback():
    """When SMTP is not configured, EmailService writes HTML preview to disk."""
    settings = EmailSettings(
        smtp_user="",
        smtp_password="",
        report_recipients="test@example.com",
    )
    service = EmailService(settings=settings)

    report = ScraperFinishedReport(
        target_type="brand",
        target_key="lenovo",
        target_name="Lenovo",
        status="SUCCESS",
        mode="Level 1",
        scraped_count=50,
        skipped_count=0,
        latest_pointers=["ThinkPad X1 Carbon", "Legion Pro 7"],
        duration_seconds=8.2,
    )

    success = service.send_scraper_finished_report(report)
    assert success is True

    # Check preview file was created in project root
    preview_file = Path(__file__).resolve().parent.parent / "latest_scraper_report.html"
    assert preview_file.exists()
    content = preview_file.read_text(encoding="utf-8")
    assert "Lenovo" in content
    assert "ThinkPad X1 Carbon" in content

    service.shutdown(wait=False)


def test_email_service_background_dispatch_is_non_blocking():
    """Verify send_scraper_finished_background returns a Future and runs asynchronously."""
    settings = EmailSettings(
        smtp_user="",
        smtp_password="",
        report_recipients="test@example.com",
    )
    service = EmailService(settings=settings)

    report = ScraperFinishedReport(
        target_type="brand",
        target_key="hp",
        target_name="HP",
        status="SUCCESS",
        mode="Level 1",
        scraped_count=30,
        skipped_count=1,
        latest_pointers=["Spectre x360", "OMEN 16"],
        duration_seconds=6.0,
    )

    calling_thread_ident = threading.get_ident()
    executed_thread_ident = []

    def mocked_send(r):
        executed_thread_ident.append(threading.get_ident())
        return True

    with patch.object(service, "send_scraper_finished_report", side_effect=mocked_send):
        future: Future[bool] = service.send_scraper_finished_background(report)

        assert isinstance(future, Future)
        result = future.result(timeout=5)
        assert result is True
        assert len(executed_thread_ident) == 1
        # Thread identity of worker must differ from main thread
        assert executed_thread_ident[0] != calling_thread_ident

    service.shutdown(wait=False)


def test_email_service_smtp_failure_is_fail_safe():
    """Verify that SMTP connection errors do not raise uncaught exceptions."""
    settings = EmailSettings(
        smtp_host="invalid.smtp.host.test",
        smtp_user="realuser@gmail.com",
        smtp_password="app_password",
        report_recipients="recipient@gmail.com",
        email_preview_mode=False,
    )
    service = EmailService(settings=settings)

    req = EmailSendRequest(
        recipients=["recipient@gmail.com"],
        subject="Test Failure",
        html_body="<p>Test</p>",
    )

    with patch("smtplib.SMTP", side_effect=OSError("Network unreachable")):
        # Must return False gracefully without raising
        result = service.send_email(req)
        assert result is False

    service.shutdown(wait=False)


# ---------------------------------------------------------------------------
# 5. Orchestrator Integration Tests (Default False Param)
# ---------------------------------------------------------------------------

def test_orchestrator_default_does_not_send_email():
    """When send_email is False (default), orchestrator does NOT dispatch emails."""
    mock_email_service = MagicMock(spec=EmailService)
    # Default orchestrator has send_email=False
    orchestrator = ScrapeOrchestrator(email_service=mock_email_service)
    assert orchestrator.send_email is False

    mock_catalog = BrandCatalogResult(
        brand="ASUS",
        official_catalog_url="https://asus.com/laptops",
        scrape_mode="level1",
        total_laptops=5,
        total_skipped=0,
        latest_pointers=["Zenbook 14"],
        laptops=[],
    )

    with patch.object(
        orchestrator,
        "_scrape_brand",
        return_value=ScrapeTargetResult(
            target_type="brand",
            target_key="asus",
            target_name="ASUS",
            level=1,
            items_scraped=5,
            brand_result=mock_catalog,
        ),
    ):
        request = ScrapeRequest(
            target_type="brand",
            targets=["asus"],
            level=1,
            # send_email is False by default
        )
        assert request.send_email is False

        response = orchestrator.execute(request)

        assert len(response.results) == 1
        # Crucial check: email dispatcher must NOT be called in local testing mode
        mock_email_service.send_scraper_finished_background.assert_not_called()


def test_orchestrator_sends_email_when_send_email_is_true():
    """When send_email=True (e.g. from API endpoint or flag), orchestrator sends emails."""
    mock_email_service = MagicMock(spec=EmailService)
    orchestrator = ScrapeOrchestrator(email_service=mock_email_service)

    mock_catalog_1 = BrandCatalogResult(
        brand="ASUS",
        official_catalog_url="https://asus.com/laptops",
        scrape_mode="level1",
        total_laptops=10,
        total_skipped=0,
        latest_pointers=["Zenbook Duo"],
        laptops=[],
    )
    mock_catalog_2 = BrandCatalogResult(
        brand="HP",
        official_catalog_url="https://hp.com/laptops",
        scrape_mode="level1",
        total_laptops=15,
        total_skipped=1,
        latest_pointers=["OMEN Transcend"],
        laptops=[],
    )

    def fake_scrape_brand(key, req):
        catalog = mock_catalog_1 if key == "asus" else mock_catalog_2
        return ScrapeTargetResult(
            target_type="brand",
            target_key=key,
            target_name=catalog.brand,
            level=req.level,
            items_scraped=catalog.total_laptops,
            brand_result=catalog,
        )

    with patch.object(orchestrator, "_scrape_brand", side_effect=fake_scrape_brand):
        # Triggered via request with send_email=True (e.g. from an endpoint)
        request = ScrapeRequest(
            target_type="brand",
            targets=["asus", "hp"],
            level=1,
            send_email=True,
        )
        response = orchestrator.execute(request)

        assert len(response.results) == 2
        assert response.total_items_scraped == 25

        # send_scraper_finished_background must be called twice (once per brand)
        assert mock_email_service.send_scraper_finished_background.call_count == 2

        calls = mock_email_service.send_scraper_finished_background.call_args_list
        report_1: ScraperFinishedReport = calls[0][0][0]
        report_2: ScraperFinishedReport = calls[1][0][0]

        assert report_1.target_name == "ASUS"
        assert report_1.scraped_count == 10
        assert report_1.skipped_count == 0

        assert report_2.target_name == "HP"
        assert report_2.scraped_count == 15
        assert report_2.skipped_count == 1
