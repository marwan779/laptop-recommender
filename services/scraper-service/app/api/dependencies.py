"""HTTP authentication helpers for the API presentation layer."""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.common.logger import get_logger
from app.core.security_config import SecuritySettings, get_security_settings

logger = get_logger("scraper.api.auth")

API_KEY_HEADER_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def validate_api_key(
    provided_key: str | None,
    settings: SecuritySettings,
) -> None:
    """Validate an incoming `X-API-Key` value against `SecuritySettings`."""
    if not settings.require_api_key:
        return

    expected = settings.scraper_api_key.strip()
    if not expected:
        logger.warning(
            "SCRAPER_API_KEY is empty while REQUIRE_API_KEY is true; "
            "protected routes will reject requests with HTTP 503."
        )
        raise HTTPException(
            status_code=503,
            detail="API key authentication is not configured",
        )

    candidate = (provided_key or "").strip()
    if not candidate or not hmac.compare_digest(
        candidate.encode("utf-8"), expected.encode("utf-8")
    ):
        logger.warning("Rejected request with a missing or invalid X-API-Key.")
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-API-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


async def verify_api_key(
    provided_key: str | None = Security(api_key_header),
    settings: SecuritySettings = Depends(get_security_settings),
) -> None:
    """FastAPI dependency wrapper delegating to `validate_api_key`."""
    validate_api_key(provided_key, settings)


__all__ = [
    "API_KEY_HEADER_NAME",
    "api_key_header",
    "validate_api_key",
    "verify_api_key",
]
