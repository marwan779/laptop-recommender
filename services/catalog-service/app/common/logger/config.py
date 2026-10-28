"""Configuration and settings for the global LoggerService."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class LogLevel(StrEnum):
    """Supported logging severity levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

    @classmethod
    def from_string(cls, level_str: str) -> LogLevel:
        """Parse case-insensitive string into LogLevel, defaulting to INFO on invalid input."""
        cleaned = level_str.strip().upper()
        if cleaned in ("WARN", "WARNING"):
            return cls.WARNING
        try:
            return cls(cleaned)
        except ValueError:
            return cls.INFO


class Environment(StrEnum):
    """Runtime execution environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"

    @classmethod
    def from_string(cls, env_str: str) -> Environment:
        """Parse environment string with common alias handling."""
        cleaned = env_str.strip().lower()
        if cleaned in ("prod", "production"):
            return cls.PRODUCTION
        if cleaned in ("stage", "staging"):
            return cls.STAGING
        if cleaned in ("test", "testing"):
            return cls.TESTING
        return cls.DEVELOPMENT


@dataclass(frozen=True)
class LoggerConfig:
    """Immutable configuration for logger initialization."""

    service_name: str = "catalog-service"
    environment: Environment = Environment.DEVELOPMENT
    version: str = "0.2.0"
    level: LogLevel = LogLevel.INFO
    json_output: bool = False
    include_caller_info: bool = True
    enable_dd_trace_injection: bool = True

    @property
    def is_production(self) -> bool:
        """Return True if executing in production or staging."""
        return self.environment in (Environment.PRODUCTION, Environment.STAGING)

    @classmethod
    def from_env(cls) -> LoggerConfig:
        """Construct LoggerConfig from standard system and Datadog environment variables."""
        service_name = os.getenv("SERVICE_NAME") or os.getenv("DD_SERVICE") or "catalog-service"
        env_raw = os.getenv("ENVIRONMENT") or os.getenv("ENV") or os.getenv("DD_ENV") or "development"
        env = Environment.from_string(env_raw)
        version = os.getenv("APP_VERSION") or os.getenv("DD_VERSION") or "0.2.0"

        # Default log level: DEBUG in dev, INFO in prod/staging/test
        default_level = "DEBUG" if env == Environment.DEVELOPMENT else "INFO"
        level_raw = os.getenv("LOG_LEVEL", default_level)
        level = LogLevel.from_string(level_raw)

        # Output format: JSON in prod/staging by default, or explicitly forced
        json_env = os.getenv("LOG_JSON_FORMAT")
        if json_env is not None:
            json_output = json_env.strip().lower() in ("true", "1", "yes")
        else:
            json_output = env in (Environment.PRODUCTION, Environment.STAGING)

        return cls(
            service_name=service_name,
            environment=env,
            version=version,
            level=level,
            json_output=json_output,
        )
