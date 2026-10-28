"""Unit tests for LoggerService, Singleton lifecycle, Datadog JSON formatter, and contextvars."""

import json
import logging
import threading
from uuid import uuid4

import pytest

from app.common.logger.config import Environment, LoggerConfig, LogLevel
from app.common.logger.context import (
    clear_context,
    get_correlation_id,
    request_context,
    set_correlation_id,
)
from app.common.logger.formatters import DatadogJSONFormatter, DevelopmentConsoleFormatter
from app.common.logger.service import LoggerService, configure_logging, get_logger


@pytest.fixture(autouse=True)
def reset_logger_singleton():
    """Ensure a clean singleton state before and after each test."""
    LoggerService._reset_instance()
    clear_context()
    yield
    LoggerService._reset_instance()
    clear_context()


def test_singleton_returns_same_instance():
    svc1 = LoggerService()
    svc2 = LoggerService()
    svc3 = LoggerService.get_instance()

    assert svc1 is svc2
    assert svc2 is svc3


def test_singleton_thread_safety():
    instances: list[LoggerService] = []

    def worker():
        instances.append(LoggerService.get_instance())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(instances) == 10
    first = instances[0]
    assert all(inst is first for inst in instances)


def test_datadog_json_formatter_structure():
    config = LoggerConfig(
        service_name="test-catalog-service",
        environment=Environment.PRODUCTION,
        version="1.0.0",
        json_output=True,
    )
    formatter = DatadogJSONFormatter(config)

    test_cid = str(uuid4())
    set_correlation_id(test_cid)

    record = logging.LogRecord(
        name="catalog.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=100,
        msg="Sample log message",
        args=(),
        exc_info=None,
    )
    record.custom_metric = 42

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["service"] == "test-catalog-service"
    assert parsed["env"] == "production"
    assert parsed["status"] == "INFO"
    assert parsed["message"] == "Sample log message"
    assert parsed["correlation_id"] == test_cid
    assert parsed["extra"]["custom_metric"] == 42


def test_context_manager_scope():
    assert get_correlation_id() is None

    cid1 = "cid-scope-1"
    with request_context(correlation_id=cid1, user_id="user_123"):
        assert get_correlation_id() == cid1

    assert get_correlation_id() is None

