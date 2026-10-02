from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseSettings):
    """Configuration for SMTP email delivery (optimized for Gmail App Password)."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_email: str = ""
    smtp_from_name: str = "Laptop Recommender Scraper"

    # Comma-separated list of recipient emails, or a single email string
    report_recipients: str = ""

    # Global master switch
    email_notifications_enabled: bool = True

    # When True or when credentials are not supplied, saves HTML to disk
    email_preview_mode: bool = False

    @property
    def is_configured(self) -> bool:
        """Return True if credentials and recipients are provided and notifications enabled."""
        has_credentials = bool(self.smtp_user.strip() and self.smtp_password.strip())
        has_recipients = bool(self.parsed_recipients)
        return self.email_notifications_enabled and has_credentials and has_recipients and not self.email_preview_mode

    @property
    def parsed_recipients(self) -> list[str]:
        """Return a clean list of recipient email addresses."""
        if not self.report_recipients:
            return []
        if isinstance(self.report_recipients, list):
            return [str(r).strip() for r in self.report_recipients if str(r).strip()]
        return [r.strip() for r in str(self.report_recipients).split(",") if r.strip()]

    @property
    def effective_from_email(self) -> str:
        """Return from email, defaulting to smtp_user if not explicitly set."""
        return self.smtp_from_email.strip() or self.smtp_user.strip() or "noreply@laptop-recommender.com"


@lru_cache(maxsize=1)
def get_email_settings() -> EmailSettings:
    """Singleton provider for EmailSettings."""
    return EmailSettings()
