"""HTTP middleware enforcing `X-API-Key` authentication on non-public routes."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.api.dependencies import API_KEY_HEADER_NAME, validate_api_key
from app.core.security_config import SecuritySettings, get_security_settings

DEFAULT_PUBLIC_PATHS: frozenset[str] = frozenset({"/health", "/ready"})


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Default-deny HTTP middleware enforcing inter-service `X-API-Key` validation."""

    def __init__(
        self,
        app: ASGIApp,
        public_paths: Iterable[str] = DEFAULT_PUBLIC_PATHS,
        header_name: str = API_KEY_HEADER_NAME,
        settings_provider: Callable[[], SecuritySettings] = get_security_settings,
    ) -> None:
        super().__init__(app)
        self.public_paths = frozenset(p.rstrip("/") or "/" for p in public_paths)
        self.header_name = header_name
        self._settings_provider = settings_provider

    def _resolve_settings(self, request: Request) -> SecuritySettings:
        app = getattr(request, "app", None)
        overrides = getattr(app, "dependency_overrides", None)
        if isinstance(overrides, dict) and get_security_settings in overrides:
            return overrides[get_security_settings]()
        return self._settings_provider()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        normalized_path = request.url.path.rstrip("/") or "/"
        if request.method == "OPTIONS" or normalized_path in self.public_paths:
            return await call_next(request)

        settings = self._resolve_settings(request)
        provided_key = request.headers.get(self.header_name)
        try:
            validate_api_key(provided_key, settings)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or {},
            )

        return await call_next(request)


__all__ = ["APIKeyAuthMiddleware", "DEFAULT_PUBLIC_PATHS"]
