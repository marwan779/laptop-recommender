"""Singleton LoggerService providing unified application-wide logging configuration."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any, Self

from app.common.logger.config import LoggerConfig
from app.common.logger.formatters import DatadogJSONFormatter, DevelopmentConsoleFormatter


class LoggerService:
    """Thread-safe Singleton managing the lifecycle and configuration of application logging."""

    _instance: LoggerService | None = None
    _lock: threading.RLock = threading.RLock()

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        """Enforce singleton instance creation across all direct instantiations."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance  # type: ignore[return-value]

    def __init__(self, config: LoggerConfig | None = None) -> None:
        """Initialize the logger service singleton (runs only once per process)."""
        if getattr(self, "_initialized", False):
            return

        with self._lock:
            if getattr(self, "_initialized", False):
                return
            self._config = config or LoggerConfig.from_env()
            self._loggers: dict[str, logging.Logger] = {}
            self._handler: logging.Handler | None = None
            self._configure_root_logger()
            self._initialized = True

    @classmethod
    def get_instance(cls, config: LoggerConfig | None = None) -> LoggerService:
        """Thread-safe accessor for the singleton LoggerService instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        elif config is not None and config != cls._instance._config:
            # Reconfigure if new configuration is explicitly supplied
            cls._instance.reconfigure(config)

        return cls._instance

    @classmethod
    def _reset_instance(cls) -> None:
        """Reset the singleton instance (primarily used for test isolation)."""
        with cls._lock:
            if cls._instance is not None:
                # Remove handlers from root logger
                root = logging.getLogger()
                if cls._instance._handler in root.handlers:
                    root.removeHandler(cls._instance._handler)
                cls._instance._handler = None
                cls._instance._initialized = False
                cls._instance = None

    @property
    def config(self) -> LoggerConfig:
        """Current active logger configuration."""
        return self._config

    def reconfigure(self, config: LoggerConfig) -> None:
        """Reconfigure active formatters, handlers, and log levels at runtime."""
        with self._lock:
            self._config = config
            self._configure_root_logger()

    def _configure_root_logger(self) -> None:
        """Set up standard library root logger and attach the appropriate stdout handler."""
        root = logging.getLogger()

        # Determine formatter based on environment and JSON toggle
        if self._config.json_output:
            formatter = DatadogJSONFormatter(self._config)
        else:
            formatter = DevelopmentConsoleFormatter(self._config)

        # Clear existing handlers managed by LoggerService or default basicConfig
        if self._handler and self._handler in root.handlers:
            root.removeHandler(self._handler)

        # Create stdout stream handler (12-factor standard for container & local logging)
        new_handler = logging.StreamHandler(sys.stdout)
        new_handler.setFormatter(formatter)
        self._handler = new_handler
        root.addHandler(new_handler)

        # Set root log level
        level_value = getattr(logging, self._config.level.value, logging.INFO)
        root.setLevel(level_value)

        # Standardize standard noise loggers
        for noisy in ("uvicorn.access", "urllib3", "boto3", "botocore", "asyncio"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    def get_logger(self, name: str | None = None) -> logging.Logger:
        """Retrieve a named logging.Logger configured to route through the Singleton LoggerService."""
        logger_name = name or self._config.service_name
        if logger_name not in self._loggers:
            with self._lock:
                if logger_name not in self._loggers:
                    logger = logging.getLogger(logger_name)
                    # Propagate to root where our configured handler processes it
                    logger.propagate = True
                    self._loggers[logger_name] = logger

        return self._loggers[logger_name]


def get_logger(name: str | None = None) -> logging.Logger:
    """Global convenience function to get a logger instance from the LoggerService singleton.

    Example:
        >>> from app.common.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Server started", extra={"port": 8000})
    """
    return LoggerService.get_instance().get_logger(name)


def configure_logging(config: LoggerConfig | None = None) -> LoggerService:
    """Explicitly initialize or reconfigure the LoggerService singleton."""
    return LoggerService.get_instance(config)
