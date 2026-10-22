"""Email Service backward compatibility proxy.

Redirects to app.notifications.service.ScraperNotificationService.
"""

from app.notifications.service import ScraperNotificationService

EmailService = ScraperNotificationService

__all__ = ["EmailService"]
