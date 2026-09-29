"""Dependency injection providers for FastAPI routes (SOLID: DIP)."""

from functools import lru_cache

from app.engine.base import IScraperEngine
from app.engine.scrapling_engine import ScraplingEngine
from app.services.email_service import EmailService
from app.services.orchestrator import ScrapeOrchestrator


@lru_cache(maxsize=1)
def get_scraper_engine() -> IScraperEngine:
    """Singleton provider for scraper engine."""
    return ScraplingEngine()


@lru_cache(maxsize=1)
def get_email_service() -> EmailService:
    """Singleton provider for email service."""
    return EmailService()


def get_orchestrator() -> ScrapeOrchestrator:
    """Provider for ScrapeOrchestrator instance.

    Injects the shared engine and email service.
    Can easily be overridden in test suites via app.dependency_overrides.
    """
    return ScrapeOrchestrator(
        engine=get_scraper_engine(),
        email_service=get_email_service(),
        send_email=False,  # Rely on ScrapeRequest.send_email
    )
