"""Log formatters for development terminal output and production Datadog JSON streams."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

from app.common.logger.config import LoggerConfig
from app.common.logger.context import get_context, get_correlation_id

# Standard attributes present on logging.LogRecord that should not be treated as user extra
_STANDARD_LOGRECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def _safe_json_default(obj: Any) -> Any:
    """Fallback JSON serializer for complex or non-standard objects."""
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, (UUID,)):
        return str(obj)
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        return obj.model_dump()
    if hasattr(obj, "dict") and callable(obj.dict):
        return obj.dict()
    if hasattr(obj, "value"):
        return obj.value
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, BaseException):
        return str(obj)
    try:
        return str(obj)
    except Exception:  # noqa: BLE001
        return "<unserializable>"


class DatadogJSONFormatter(logging.Formatter):
    """Production JSON formatter adhering to Datadog Standard Log Attributes."""

    def __init__(self, config: LoggerConfig) -> None:
        super().__init__()
        self.config = config

    def format(self, record: logging.LogRecord) -> str:
        # 1. Base Datadog log payload
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "status": record.levelname,
            "message": record.getMessage(),
            "service": self.config.service_name,
            "env": self.config.environment.value,
            "version": self.config.version,
            "logger": {
                "name": record.name,
                "thread_name": record.threadName,
            },
        }

        # 2. Source code location details
        if self.config.include_caller_info:
            log_entry["logger"]["file_name"] = record.filename
            log_entry["logger"]["line_number"] = record.lineno
            log_entry["logger"]["method_name"] = record.funcName

        # 3. Correlation ID & request context
        correlation_id = get_correlation_id()
        if correlation_id:
            log_entry["correlation_id"] = correlation_id

        bound_context = get_context()
        if bound_context:
            log_entry["context"] = bound_context

        # 4. Optional Datadog APM trace/span injection
        if self.config.enable_dd_trace_injection:
            try:
                from ddtrace import tracer

                span = tracer.current_span()
                if span:
                    log_entry["dd"] = {
                        "trace_id": str(span.trace_id),
                        "span_id": str(span.span_id),
                    }
            except Exception:  # noqa: BLE001, S110
                pass

        # 5. Extract custom extra attributes passed to logger call
        extra_attrs: dict[str, Any] = {}
        for key, val in record.__dict__.items():
            if key not in _STANDARD_LOGRECORD_ATTRS and not key.startswith("_"):
                extra_attrs[key] = val

        if extra_attrs:
            log_entry["extra"] = extra_attrs

        # 6. Exception & Stack trace handling
        if record.exc_info:
            exc_type, exc_val, _ = record.exc_info
            log_entry["error"] = {
                "kind": exc_type.__name__ if exc_type else "Exception",
                "message": str(exc_val) if exc_val else "",
                "stack": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry, default=_safe_json_default, ensure_ascii=False)


class DevelopmentConsoleFormatter(logging.Formatter):
    """Human-friendly colored formatter for local development and terminal debugging."""

    # ANSI color codes
    _COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31;1m",  # Bold Red
    }
    _DIM: str = "\033[2m"
    _CYAN: str = "\033[36m"
    _MAGENTA: str = "\033[35m"
    _RESET: str = "\033[0m"

    def __init__(self, config: LoggerConfig, use_colors: bool = True) -> None:
        super().__init__()
        self.config = config
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        # Timestamp
        time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]

        level = record.levelname
        msg = record.getMessage()

        # Correlation ID badge
        correlation_id = get_correlation_id()
        cid_badge = f" [cid:{correlation_id}]" if correlation_id else ""

        # Location
        location = f"{record.filename}:{record.lineno}"

        if self.use_colors:
            color = self._COLORS.get(level, "")
            formatted = (
                f"{self._DIM}{time_str}{self._RESET} "
                f"{color}{level:<7}{self._RESET} "
                f"{self._CYAN}[{record.name}]{self._RESET} "
                f"{self._DIM}({location}){self._RESET}"
                f"{self._MAGENTA}{cid_badge}{self._RESET} "
                f"- {msg}"
            )
        else:
            formatted = f"{time_str} {level:<7} [{record.name}] ({location}){cid_badge} - {msg}"

        # Extra attributes
        extra_attrs: dict[str, Any] = {}
        for key, val in record.__dict__.items():
            if key not in _STANDARD_LOGRECORD_ATTRS and not key.startswith("_"):
                extra_attrs[key] = val

        bound_context = get_context()
        if bound_context:
            extra_attrs.update(bound_context)

        if extra_attrs:
            formatted += f" {self._DIM}| {extra_attrs}{self._RESET}" if self.use_colors else f" | {extra_attrs}"

        # Exceptions
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted
