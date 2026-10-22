"""Dependency injection providers for FastAPI routes (SOLID: DIP)."""

from functools import lru_cache

from app.engine.base import IScraperEngine
from app.engine.scrapling_engine import ScraplingEngine
from app.notifications.service import ScraperNotificationService
from app.services.orchestrator import ScrapeOrchestrator
from app.common.storage.base import IObjectStorageService


@lru_cache(maxsize=1)
def get_scraper_engine() -> IScraperEngine:
    """Singleton provider for scraper engine."""
    return ScraplingEngine()


@lru_cache(maxsize=1)
def get_email_service() -> ScraperNotificationService:
    """Singleton provider for email service."""
    return ScraperNotificationService()


def get_orchestrator() -> ScrapeOrchestrator:
    """Provider for ScrapeOrchestrator instance.

    Injects the shared engine, email service, and storage service.
    Can easily be overridden in test suites via app.dependency_overrides.
    """
    return ScrapeOrchestrator(
        engine=get_scraper_engine(),
        email_service=get_email_service(),
        send_email=False,  # Rely on ScrapeRequest.send_email
        storage_service=get_storage(),
        upload_to_bucket=False,  # Rely on ScrapeRequest.upload_to_bucket
    )


def get_storage() -> "IObjectStorageService":
    """Provider for object storage service (AWS S3 / S3-compatible)."""
    from app.common.storage.factory import get_storage_service

    return get_storage_service()
