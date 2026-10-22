"""Scraper notifications package for report generation and dispatch."""

from app.notifications.service import ScraperNotificationService
from app.notifications.templates import (
    build_batch_finished_email,
    build_single_finished_email,
)

__all__ = [
    "ScraperNotificationService",
    "build_batch_finished_email",
    "build_single_finished_email",
]

