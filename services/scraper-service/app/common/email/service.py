"""Generic Email Transport Service with background thread execution."""

from __future__ import annotations

import atexit
from concurrent.futures import Future, ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
import smtplib

from app.common.logger import get_logger
from app.core.email_config import EmailSettings, get_email_settings
from app.schemas.email import EmailSendRequest

logger = get_logger("common.email")


class EmailService:
    """Generic SMTP delivery service with non-blocking background queue support."""

    def __init__(
        self,
        settings: EmailSettings | None = None,
        preview_filename: str = "latest_scraper_report.html",
        max_workers: int = 2,
    ) -> None:
        self.settings = settings or get_email_settings()
        self.preview_filename = preview_filename
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="email_worker")
        atexit.register(self.shutdown, wait=True)

    @property
    def is_enabled(self) -> bool:
        """Return True if notifications are globally enabled."""
        return self.settings.email_notifications_enabled

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the background thread pool."""
        try:
            self._executor.shutdown(wait=wait)
        except Exception:  # noqa: S110
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
            return True

        except Exception as exc:
            logger.error("Failed to deliver email: %s", exc, exc_info=True)
            # As a fallback, save the preview so the user still has visibility
            self._save_preview_html(req)
            return False

    def send_email_background(self, req: EmailSendRequest) -> Future[bool]:
        """Dispatch email delivery asynchronously to the background worker pool."""
        return self._executor.submit(self._safe_background_send, req)

    def _safe_background_send(self, req: EmailSendRequest) -> bool:
        """Internal worker function wrapped in try/except to prevent worker thread crashes."""
        try:
            return self.send_email(req)
        except Exception as exc:
            logger.error("Background email worker error: %s", exc, exc_info=True)
            return False

    def _save_preview_html(self, req: EmailSendRequest, filename: str | None = None) -> Path:
        """Save HTML email to disk for debugging and preview."""
        target_name = filename or self.preview_filename
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        preview_file = project_root / target_name
        try:
            preview_file.write_text(req.html_body, encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not write preview HTML file: %s", exc)
        return preview_file
