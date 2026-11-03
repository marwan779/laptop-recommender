"""Request logging and correlation ID tracking middleware."""

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.common.logger import clear_context, get_logger, set_correlation_id

logger = get_logger("catalog.api.access")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware ensuring every request has a correlation ID and structured latency log."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        set_correlation_id(correlation_id)

        start_time = time.perf_counter()
        logger.info(
            "HTTP %s %s started",
            request.method,
            request.url.path,
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "client_ip": request.client.host if request.client else None,
            },
        )

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            response.headers["X-Correlation-ID"] = correlation_id
            logger.info(
                "HTTP %s %s completed [status=%d, duration=%.2fms]",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={
                    "http_status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "HTTP %s %s unhandled exception: %s [duration=%.2fms]",
                request.method,
                request.url.path,
                exc,
                duration_ms,
                exc_info=True,
                extra={
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise
        finally:
            clear_context()
