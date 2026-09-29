"""Email Service with background thread execution for scraper status notifications.

Provides non-blocking email delivery via ThreadPoolExecutor so that scraping threads
are never held up by network latency or SMTP handshakes.
"""

from __future__ import annotations

import atexit
from concurrent.futures import Future, ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
import logging
from pathlib import Path
import smtplib

from app.core.email_config import EmailSettings, get_email_settings
from app.email.templates import (
    build_batch_finished_email,
    build_single_finished_email,
)
from app.schemas.email import (
    BatchScrapeReport,
    EmailSendRequest,
    ScraperFinishedReport,
)

logger = logging.getLogger("scraper.email")


class EmailService:
    """Service responsible for rendering and delivering scraper notification emails."""

    def __init__(
        self,
        settings: EmailSettings | None = None,
        preview_filename: str = "latest_scraper_report.html",
    ) -> None:
        self.settings = settings or get_email_settings()
        self.preview_filename = preview_filename
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email_worker")
        atexit.register(self.shutdown, wait=True)

    @property
    def is_enabled(self) -> bool:
        """Return True if notifications are globally enabled."""
        return self.settings.email_notifications_enabled

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the background thread pool."""
        try:
            self._executor.shutdown(wait=wait)
        except Exception:
            pass

    def send_email(self, req: EmailSendRequest) -> bool:
        """Send an email synchronously.

        If SMTP credentials are not configured or preview mode is active,
        the email HTML is saved to disk as a preview file.

        Returns:
            bool: True if delivered or previewed successfully, False on error.
        """
        if not self.is_enabled:
            logger.info("Email notifications are disabled via settings. Skipping.")
            return False

        if not self.settings.is_configured:
            # Save preview file for inspection
            preview_path = self._save_preview_html(req)
            msg = f"[EmailService] Preview mode: Saved email preview to {preview_path.name}"
            logger.info(msg)
            print(msg)
            return True

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = req.subject

            from_name = req.from_name or self.settings.smtp_from_name
            from_email = req.from_email or self.settings.effective_from_email
            msg["From"] = formataddr((from_name, from_email))
            msg["To"] = ", ".join(req.recipients)

            if req.cc:
                msg["Cc"] = ", ".join(req.cc)

            # Plain text alternative
            if req.text_body:
                msg.attach(MIMEText(req.text_body, "plain", "utf-8"))

            # HTML primary
            msg.attach(MIMEText(req.html_body, "html", "utf-8"))

            all_destinations = list(req.recipients) + list(req.cc) + list(req.bcc)

            # Connect via SMTP (SSL for port 465, STARTTLS for 587/25)
            if self.settings.smtp_port == 465:
                server = smtplib.SMTP_SSL(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                    timeout=15,
                )
            else:
                server = smtplib.SMTP(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                    timeout=15,
                )
                if self.settings.smtp_use_tls:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()

            if self.settings.smtp_user and self.settings.smtp_password:
                server.login(self.settings.smtp_user, self.settings.smtp_password)

            server.send_message(msg, to_addrs=all_destinations)
            server.quit()

            success_msg = f"[EmailService] Email report sent to {req.recipients}"
            logger.info(success_msg)
            print(success_msg)
            return True

        except Exception as exc:
            logger.error("Failed to deliver email: %s", exc, exc_info=True)
            print(f"[EmailService] Error delivering email: {exc}")
            # As a fallback, save the preview so the user still has visibility
            self._save_preview_html(req)
            return False

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

    def send_scraper_finished_background(
        self, report: ScraperFinishedReport
    ) -> Future[bool]:
        """Dispatch a single scraper finished report to the background thread pool.

        Returns immediately with a Future without blocking the scraping pipeline.
        """
        print(f"[EmailService] Background email job dispatched for '{report.target_name}' [{report.status}]...")
        return self._executor.submit(self._safe_background_send, report)

    def _safe_background_send(self, report: ScraperFinishedReport) -> bool:
        """Internal worker function wrapped in try/except to prevent thread crashes."""
        try:
            return self.send_scraper_finished_report(report)
        except Exception as exc:
            logger.error(
                "Background email worker error for '%s': %s",
                report.target_name,
                exc,
                exc_info=True,
            )
            print(f"[EmailService] Worker exception for '{report.target_name}': {exc}")
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

    def _save_preview_html(
        self, req: EmailSendRequest, filename: str | None = None
    ) -> Path:
        """Save HTML email to disk for debugging and preview."""
        target_name = filename or self.preview_filename
        project_root = Path(__file__).resolve().parent.parent.parent
        preview_file = project_root / target_name
        try:
            preview_file.write_text(req.html_body, encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not write preview HTML file: %s", exc)
        return preview_file
