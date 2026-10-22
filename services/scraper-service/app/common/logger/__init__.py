"""Global Unified Logging Service for Laptop Recommender."""

from app.common.logger.config import Environment, LoggerConfig, LogLevel
from app.common.logger.context import (
    bind_context,
    clear_context,
    get_context,
    get_correlation_id,
    request_context,
    set_correlation_id,
)
from app.common.logger.formatters import DatadogJSONFormatter, DevelopmentConsoleFormatter
from app.common.logger.service import (
    LoggerService,
    configure_logging,
    get_logger,
)

__all__ = [
    "DatadogJSONFormatter",
    "DevelopmentConsoleFormatter",
    "Environment",
    "LogLevel",
    "LoggerConfig",
    "LoggerService",
    "bind_context",
    "clear_context",
    "configure_logging",
    "get_context",
    "get_correlation_id",
    "get_logger",
    "request_context",
    "set_correlation_id",
]
