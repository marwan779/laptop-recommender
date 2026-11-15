"""HTTP middleware package for `scraper-service` (one middleware class per module)."""

from app.api.middlewares.api_key_auth import APIKeyAuthMiddleware, DEFAULT_PUBLIC_PATHS

__all__ = ["APIKeyAuthMiddleware", "DEFAULT_PUBLIC_PATHS"]
