"""Scraper Notification Service for rendering and dispatching status emails."""

from __future__ import annotations

from concurrent.futures import Future

from app.common.email.service import EmailService
from app.common.logger import get_logger
from app.core.email_config import EmailSettings
from app.notifications.templates import (
    build_batch_finished_email,
    build_single_finished_email,
)
from app.schemas.email import (
    BatchScrapeReport,
    EmailSendRequest,
    ScraperFinishedReport,
)

logger = get_logger("scraper.notifications")


class ScraperNotificationService(EmailService):
    """Service responsible for rendering scraper metrics into HTML reports and dispatching them."""

    def __init__(
        self,
        settings: EmailSettings | None = None,
        preview_filename: str = "latest_scraper_report.html",
        max_workers: int = 2,
    ) -> None:
        super().__init__(
            settings=settings,
            preview_filename=preview_filename,
            max_workers=max_workers,
        )

    def send_scraper_finished_report(self, report: ScraperFinishedReport) -> bool:
        """Render and deliver a single scraper finished report synchronously."""
        subject, html_body, text_body = build_single_finished_email(report)
        recipients = self.settings.parsed_recipients or ["preview@laptop-recommender.local"]

        req = EmailSendRequest(
            recipients=recipients,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            from_email=self.settings.effective_from_email,
            from_name=self.settings.smtp_from_name,
        )
        return self.send_email(req)

    def send_scraper_finished_background(self, report: ScraperFinishedReport) -> Future[bool]:
        """Dispatch a single scraper finished report to the background thread pool."""
        logger.info(
            "Background email job dispatched for '%s' [%s]...",
            report.target_name,
            report.status,
        )
        return self._executor.submit(self._safe_background_send, report)

    def _safe_background_send(self, report: ScraperFinishedReport) -> bool:
        """Internal worker function wrapped in try/except to prevent worker thread crashes."""
        try:
            return self.send_scraper_finished_report(report)
        except Exception as exc:
            logger.error(
                "Background notification worker error for '%s': %s",
                report.target_name,
                exc,
                exc_info=True,
            )
            return False

    def send_batch_report(
        self,
        report: BatchScrapeReport,
        recipients: list[str] | None = None,
    ) -> bool:
        """Generate and dispatch a consolidated batch report email."""
        if not self.is_enabled:
            return False

        target_recipients = recipients or self.settings.parsed_recipients
        if not target_recipients and not self.settings.is_configured:
            target_recipients = ["preview@local"]

        subject, html_body, text_body = build_batch_finished_email(report)

        req = EmailSendRequest(
            recipients=target_recipients,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            from_email=self.settings.effective_from_email,
            from_name=self.settings.smtp_from_name,
        )
        return self.send_email(req)

