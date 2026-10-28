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
        return cls._instance

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
            cls._instance.reconfigure(config)

        return cls._instance

    @classmethod
    def _reset_instance(cls) -> None:
        """Reset the singleton instance (primarily used for test isolation)."""
        with cls._lock:
            if cls._instance is not None:
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

        if self._config.json_output:
            formatter = DatadogJSONFormatter(self._config)
        else:
            formatter = DevelopmentConsoleFormatter(self._config)

        if self._handler and self._handler in root.handlers:
            root.removeHandler(self._handler)

        new_handler = logging.StreamHandler(sys.stdout)
        new_handler.setFormatter(formatter)
        self._handler = new_handler
        root.addHandler(new_handler)

        log_level_int = getattr(logging, self._config.level.value, logging.INFO)
        root.setLevel(log_level_int)

    def get_logger(self, name: str) -> logging.Logger:
        """Retrieve a configured logger instance bound to the application logging hierarchy."""
        with self._lock:
            if name not in self._loggers:
                self._loggers[name] = logging.getLogger(name)
            return self._loggers[name]


def configure_logging(config: LoggerConfig | None = None) -> LoggerService:
    """Bootstrap the global unified logging subsystem."""
    return LoggerService.get_instance(config)


def get_logger(name: str) -> logging.Logger:
    """Fast accessor for retrieving a named logger instance."""
    return LoggerService.get_instance().get_logger(name)

