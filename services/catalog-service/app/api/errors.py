"""Global API exception handlers for structured error responses."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.logger import get_correlation_id, get_logger

logger = get_logger("catalog.api.errors")


def setup_exception_handlers(app: FastAPI) -> None:
    """Register uniform error handlers across the FastAPI application."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        correlation_id = get_correlation_id()
        logger.warning(
            "HTTP %d on %s: %s",
            exc.status_code,
            request.url.path,
            exc.detail,
            extra={
                "http_status": exc.status_code,
                "http_path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.status_code,
                    "message": exc.detail,
                    "correlation_id": correlation_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        correlation_id = get_correlation_id()
        logger.warning(
            "Validation error on %s: %s",
            request.url.path,
            exc.errors(),
            extra={
                "http_status": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "http_path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "message": "Validation failed",
                    "details": exc.errors(),
                    "correlation_id": correlation_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = get_correlation_id()
        logger.critical(
            "Unhandled server error on %s: %s",
            request.url.path,
            exc,
            exc_info=True,
            extra={
                "http_status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "http_path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Internal server error",
                    "correlation_id": correlation_id,
                }
            },
        )
