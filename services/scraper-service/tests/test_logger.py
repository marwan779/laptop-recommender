"""Unit tests for LoggerService, Singleton lifecycle, Datadog JSON formatter, and contextvars."""

import json
import logging
import threading
from datetime import UTC, datetime
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


# ─────────────────────────────────────────────────────────────
# 1. Singleton Lifecycle Tests
# ─────────────────────────────────────────────────────────────


def test_singleton_returns_same_instance():
    """Verify that multiple instantiations and get_instance() return the identical singleton."""
    svc1 = LoggerService()
    svc2 = LoggerService()
    svc3 = LoggerService.get_instance()

    assert svc1 is svc2
    assert svc2 is svc3


def test_singleton_thread_safety():
    """Verify that concurrent threads accessing get_instance receive the exact same singleton instance."""
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
    for inst in instances:
        assert inst is first


# ─────────────────────────────────────────────────────────────
# 2. Configuration & 4 Severity Levels
# ─────────────────────────────────────────────────────────────


def test_log_level_parsing():
    """Verify parsing of 4 standard levels: DEBUG, INFO, WARNING, ERROR."""
    assert LogLevel.from_string("debug") == LogLevel.DEBUG
    assert LogLevel.from_string("INFO") == LogLevel.INFO
    assert LogLevel.from_string("warn") == LogLevel.WARNING
    assert LogLevel.from_string("warning") == LogLevel.WARNING
    assert LogLevel.from_string("error") == LogLevel.ERROR
    assert LogLevel.from_string("UNKNOWN") == LogLevel.INFO


def test_logger_levels_filter_correctly(capsys):
    """Verify that logger honors the configured log level and supports all 4 levels."""
    cfg = LoggerConfig(
        service_name="test-service",
        environment=Environment.DEVELOPMENT,
        level=LogLevel.WARNING,
        json_output=False,
    )
    svc = LoggerService.get_instance(cfg)
    logger = svc.get_logger("test.filter")

    logger.debug("debug message - should be ignored")
    logger.info("info message - should be ignored")
    logger.warning("warning message - should appear")
    logger.error("error message - should appear")

    captured = capsys.readouterr().out
    assert "debug message" not in captured
    assert "info message" not in captured
    assert "warning message" in captured
    assert "error message" in captured


# ─────────────────────────────────────────────────────────────
# 3. Production Datadog JSON Formatter
# ─────────────────────────────────────────────────────────────


def test_datadog_json_formatter_structure():
    """Verify Datadog JSON output conforms to required standard schema."""
    cfg = LoggerConfig(
        service_name="scraper-service",
        environment=Environment.PRODUCTION,
        version="2.1.0",
        level=LogLevel.DEBUG,
        json_output=True,
    )
    formatter = DatadogJSONFormatter(cfg)

    record = logging.LogRecord(
        name="app.scraper",
        level=logging.INFO,
        pathname="services/scraper-service/app/scrapers/asus.py",
        lineno=42,
        msg="Scraped %d products from %s",
        args=(15, "Asus Store"),
        exc_info=None,
    )
    record.funcName = "scrape_all"

    output = formatter.format(record)
    data = json.loads(output)

    assert data["status"] == "INFO"
    assert data["message"] == "Scraped 15 products from Asus Store"
    assert data["service"] == "scraper-service"
    assert data["env"] == "production"
    assert data["version"] == "2.1.0"
    assert data["logger"]["name"] == "app.scraper"
    assert data["logger"]["file_name"] == "asus.py"
    assert data["logger"]["line_number"] == 42
    assert data["logger"]["method_name"] == "scrape_all"
    assert "timestamp" in data
    assert data["timestamp"].endswith("Z")


def test_datadog_json_formatter_with_exception():
    """Verify exceptions are formatted into Datadog standard error block."""
    cfg = LoggerConfig(
        service_name="catalog-service",
        environment=Environment.PRODUCTION,
        json_output=True,
    )
    formatter = DatadogJSONFormatter(cfg)

    try:
        raise ValueError("Invalid laptop payload")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="app.catalog",
        level=logging.ERROR,
        pathname="catalog.py",
        lineno=10,
        msg="Database insertion failed",
        args=(),
        exc_info=exc_info,
    )

    data = json.loads(formatter.format(record))
    assert data["status"] == "ERROR"
    assert "error" in data
    assert data["error"]["kind"] == "ValueError"
    assert data["error"]["message"] == "Invalid laptop payload"
    assert "Traceback" in data["error"]["stack"]


def test_datadog_json_formatter_safe_serialization():
    """Verify arbitrary custom objects (UUID, datetime, set) serialize without error."""
    cfg = LoggerConfig(json_output=True)
    formatter = DatadogJSONFormatter(cfg)

    class CustomModel:
        def model_dump(self):
            return {"nested": "value"}

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Complex extra payload",
        args=(),
        exc_info=None,
    )
    record.my_uuid = uuid4()
    record.now = datetime.now(UTC)
    record.unique_tags = {"tag1", "tag2"}
    record.custom = CustomModel()

    data = json.loads(formatter.format(record))
    assert "extra" in data
    assert "my_uuid" in data["extra"]
    assert "now" in data["extra"]
    assert isinstance(data["extra"]["unique_tags"], list)
    assert data["extra"]["custom"] == {"nested": "value"}


# ─────────────────────────────────────────────────────────────
# 4. Development Console Formatter
# ─────────────────────────────────────────────────────────────


def test_development_console_formatter_output():
    """Verify development console formatter renders human-readable output."""
    cfg = LoggerConfig(
        service_name="scraper-service",
        environment=Environment.DEVELOPMENT,
        json_output=False,
    )
    formatter = DevelopmentConsoleFormatter(cfg, use_colors=False)

    record = logging.LogRecord(
        name="app.normalizer",
        level=logging.INFO,
        pathname="app/core/normalizer.py",
        lineno=88,
        msg="Normalized memory to 16GB",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    assert "INFO" in output
    assert "[app.normalizer]" in output
    assert "normalizer.py:88" in output
    assert "Normalized memory to 16GB" in output


# ─────────────────────────────────────────────────────────────
# 5. Correlation ID & Context Propagation
# ─────────────────────────────────────────────────────────────


def test_correlation_id_in_datadog_json():
    """Verify correlation ID is automatically injected into JSON output."""
    cfg = LoggerConfig(json_output=True)
    formatter = DatadogJSONFormatter(cfg)

    record = logging.LogRecord(
        name="api",
        level=logging.INFO,
        pathname="api.py",
        lineno=1,
        msg="Handling scrape request",
        args=(),
        exc_info=None,
    )

    # Without correlation ID
    data1 = json.loads(formatter.format(record))
    assert "correlation_id" not in data1

    # With correlation ID set
    set_correlation_id("req-12345-abc")
    data2 = json.loads(formatter.format(record))
    assert data2["correlation_id"] == "req-12345-abc"


def test_request_context_manager():
    """Verify request_context binds and restores context and correlation ID."""
    assert get_correlation_id() is None

    with request_context(correlation_id="ctx-test-999", store="btech"):
        assert get_correlation_id() == "ctx-test-999"

        cfg = LoggerConfig(json_output=True)
        formatter = DatadogJSONFormatter(cfg)
        record = logging.LogRecord("test", logging.INFO, "t.py", 1, "test", (), None)
        data = json.loads(formatter.format(record))

        assert data["correlation_id"] == "ctx-test-999"
        assert data["context"]["store"] == "btech"

    # Restored
    assert get_correlation_id() is None


# ─────────────────────────────────────────────────────────────
# 6. Global Helper and Convenience API
# ─────────────────────────────────────────────────────────────


def test_global_get_logger_api(capsys):
    """Verify top-level get_logger helper functions cleanly across modules."""
    configure_logging(
        LoggerConfig(
            service_name="my-app",
            environment=Environment.DEVELOPMENT,
            level=LogLevel.DEBUG,
            json_output=False,
        )
    )

    logger = get_logger("my.module")
    logger.info("Application initialized successfully", extra={"port": 8000})

    out = capsys.readouterr().out
    assert "my.module" in out
    assert "Application initialized successfully" in out
    assert "port" in out
