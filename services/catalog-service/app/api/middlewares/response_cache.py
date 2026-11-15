"""HTTP response caching middleware for read-heavy catalog and recommendation endpoints."""

import hashlib
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.common.cache.provider import ICacheProvider
from app.common.logger import get_logger
from app.core.config import settings

cache_logger = get_logger("catalog.api.cache")


class ResponseCacheMiddleware(BaseHTTPMiddleware):
    """HTTP response caching middleware for read-heavy catalog and recommendation endpoints.

    Behavior:
    1. Intercepts whitelisted read endpoints:
       - GET /api/v1/laptops/{laptop_id} (and /api/v1/catalog/laptops/{laptop_id})
       - GET /api/v1/laptops/{laptop_id}/price-history (and /api/v1/catalog/laptops/{laptop_id}/price-history)
       - GET /api/v1/laptops (and /api/v1/catalog/laptops)
       - POST /api/v1/recommendations
    2. Computes a strict SHA-256 fingerprint from the exact request (method, path, query, raw body).
       Only 100% matching requests map to the same cache entry; any small difference produces a new entry.
    3. On HIT: returns cached JSON payload immediately with `X-Cache: HIT`.
    4. On MISS: forwards request to the route handler, caches 200 OK response bytes,
       and returns the response with `X-Cache: MISS`.
    """

    def __init__(
        self,
        app,
        cache_provider: ICacheProvider | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        super().__init__(app)
        self.cache_provider = cache_provider
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else settings.cache_default_ttl_seconds

    @staticmethod
    def _match_cacheable_prefix(method: str, path: str) -> str | None:
        """Return cache namespace prefix if the route is cacheable, else None."""
        prefix = settings.api_prefix
        norm_path = path.rstrip("/")
        if method == "GET":
            if norm_path == f"{prefix}/laptops" or norm_path == f"{prefix}/catalog/laptops":
                return "catalog:browse"
            if norm_path.endswith("/price-history"):
                return "catalog:price_history"
            if path.startswith(f"{prefix}/laptops/") or path.startswith(f"{prefix}/catalog/laptops/"):
                return "catalog:laptop"
        if method == "POST" and norm_path == f"{prefix}/recommendations":
            return "catalog:recommendation"
        return None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.enable_cache:
            return await call_next(request)

        key_prefix = self._match_cacheable_prefix(request.method, request.url.path)
        if key_prefix is None:
            return await call_next(request)

        cache: ICacheProvider | None = getattr(request.app.state, "cache", None) or self.cache_provider
        if cache is None:
            return await call_next(request)

        # Build strict 100%-exact SHA-256 request fingerprint
        raw_body = await request.body() if request.method == "POST" else b""
        fingerprint = f"{request.method}:{request.url.path}?{request.url.query}:".encode() + raw_body
        digest = hashlib.sha256(fingerprint).hexdigest()
        cache_key = f"{key_prefix}:{digest}"

        lookup_start = time.perf_counter()
        cached_payload = await cache.get(cache_key)
        lookup_ms = (time.perf_counter() - lookup_start) * 1000

        if cached_payload is not None:
            cache_logger.info(
                "Cache HIT for %s %s [key=%s, lookup=%.2fms]",
                request.method,
                request.url.path,
                cache_key,
                lookup_ms,
            )
            return Response(
                content=cached_payload,
                status_code=200,
                media_type="application/json",
                headers={
                    "X-Cache": "HIT",
                    "X-Cache-Key": cache_key,
                    "X-Cache-Lookup-Time-Ms": f"{lookup_ms:.2f}",
                },
            )

        # Cache MISS -> execute downstream route handler
        response = await call_next(request)

        if response.status_code != 200:
            response.headers["X-Cache"] = "MISS"
            return response

        # Read and buffer 200 OK response stream before sending to user
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
        response_bytes = b"".join(chunks)

        await cache.set(cache_key, response_bytes, ttl_seconds=self.ttl_seconds)
        cache_logger.info(
            "Cache MISS -> stored %s %s [key=%s, bytes=%d, ttl=%ds]",
            request.method,
            request.url.path,
            cache_key,
            len(response_bytes),
            self.ttl_seconds,
        )

        headers = dict(response.headers)
        headers["X-Cache"] = "MISS"
        headers["X-Cache-Key"] = cache_key
        headers["X-Cache-Lookup-Time-Ms"] = f"{lookup_ms:.2f}"

        return Response(
            content=response_bytes,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type or "application/json",
        )
