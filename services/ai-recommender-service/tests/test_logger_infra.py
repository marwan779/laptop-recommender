"""Tests for the shared unified logger infrastructure."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import pytest

from app.common.logger import (
    DatadogJSONFormatter,
    Environment,
    LoggerConfig,
    LoggerService,
    LogLevel,
    bind_context,
    clear_context,
    get_context,
    get_correlation_id,
    get_logger,
    request_context,
)


@pytest.fixture(autouse=True)
def reset_logger_state() -> None:
    """Reset singleton/service state and logging context around every test."""
    LoggerService._reset_instance()
    clear_context()
    yield
    LoggerService._reset_instance()
    clear_context()


def _clear_logger_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SERVICE_NAME",
        "DD_SERVICE",
        "ENVIRONMENT",
        "ENV",
        "DD_ENV",
        "APP_VERSION",
        "DD_VERSION",
        "LOG_LEVEL",
        "LOG_JSON_FORMAT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_logger_config_from_env_defaults_and_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_logger_env(monkeypatch)

    config = LoggerConfig.from_env()
    assert config.service_name == "ai-recommender-service"
    assert config.environment is Environment.DEVELOPMENT
    assert config.level is LogLevel.DEBUG
    assert config.json_output is False
    assert config.is_production is False

    monkeypatch.setenv("ENVIRONMENT", "prod")
    production = LoggerConfig.from_env()
    assert production.environment is Environment.PRODUCTION
    assert production.is_production is True
    assert production.json_output is True

    monkeypatch.setenv("ENVIRONMENT", "staging")
    staging = LoggerConfig.from_env()
    assert staging.environment is Environment.STAGING
    assert staging.json_output is True

    monkeypatch.setenv("ENVIRONMENT", "test")
    testing = LoggerConfig.from_env()
    assert testing.environment is Environment.TESTING
    assert testing.is_production is False
    assert testing.json_output is False

    assert LogLevel.from_string("warn") is LogLevel.WARNING
    assert LogLevel.from_string("WARNING") is LogLevel.WARNING
    assert LogLevel.from_string("not-a-level") is LogLevel.INFO


def test_request_context_sets_and_restores_correlation_and_metadata() -> None:
    assert get_correlation_id() is None
    assert get_context() == {}

    bind_context(service="ai-recommender")
    assert get_context() == {"service": "ai-recommender"}

    with request_context(correlation_id="cid-outer", user_id=42):
        assert get_correlation_id() == "cid-outer"
        assert get_context() == {"service": "ai-recommender", "user_id": 42}

        with request_context(correlation_id="cid-inner", operation="enrich"):
            assert get_correlation_id() == "cid-inner"
            assert get_context() == {
                "service": "ai-recommender",
                "user_id": 42,
                "operation": "enrich",
            }

        assert get_correlation_id() == "cid-outer"
        assert get_context() == {"service": "ai-recommender", "user_id": 42}

    assert get_correlation_id() is None
    assert get_context() == {"service": "ai-recommender"}


def test_datadog_json_formatter_emits_expected_payload() -> None:
    config = LoggerConfig(
        service_name="ai-recommender-service",
        environment=Environment.PRODUCTION,
        version="1.2.3",
        level=LogLevel.INFO,
        json_output=True,
    )
    record = logging.LogRecord(
        name="ai_recommender.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="enriched %s chassis",
        args=("12",),
        exc_info=None,
    )

    with request_context(correlation_id="corr-123", job_id="job-7"):
        rendered = DatadogJSONFormatter(config).format(record)

    payload: Dict[str, Any] = json.loads(rendered)
    assert payload["message"] == "enriched 12 chassis"
    # Datadog standard uses `status` as the severity/level field.
    assert payload.get("level", payload.get("status")) == "INFO"
    assert payload["service"] == "ai-recommender-service"
    assert payload["env"] == "production"
    assert payload["version"] == "1.2.3"
    assert payload["correlation_id"] == "corr-123"
    assert payload["context"] == {"job_id": "job-7"}
    assert payload["logger"]["name"] == "ai_recommender.test"


def test_get_logger_and_logger_service_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_logger_env(monkeypatch)

    logger = get_logger("ai_recommender.test")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "ai_recommender.test"

    first = LoggerService.get_instance()
    second = LoggerService.get_instance()
    third = LoggerService()

    assert first is second
    assert first is third
    assert first.config.service_name == "ai-recommender-service"
    assert first.get_logger("ai_recommender.test") is logger
