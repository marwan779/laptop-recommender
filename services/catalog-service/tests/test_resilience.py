"""Tests for the Catalog Microservice Resilience Framework."""

from app.common.resilience import (
    BatchCircuitBreaker,
    CircuitBreakerTrippedError,
    DeadLetterQuarantine,
    ErrorCategory,
    ErrorSeverity,
    RecoveryAction,
    ServiceErrorRecord,
    extract_status_code,
    resilient_boundary,
    resilient_step,
)


class DummyHTTPError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def test_status_code_extraction():
    assert extract_status_code(ValueError("Standard error")) is None
    assert extract_status_code(DummyHTTPError("Rate limited", 429)) == 429


def test_service_error_record_creation():
    record = ServiceErrorRecord(
        category=ErrorCategory.DATABASE,
        source_component="catalog.database",
        exception_type="OperationalError",
        exception_message="Connection timeout",
        traceback="traceback content",
    )
    assert record.category == ErrorCategory.DATABASE
    assert record.severity == ErrorSeverity.ERROR
    assert record.recovery_action == RecoveryAction.QUARANTINED
    assert record.error_id is not None


def test_resilient_boundary_swallows_and_records():
    dlq = DeadLetterQuarantine(target_key="catalog_test", target_type="scoring")

    with resilient_boundary(
        category=ErrorCategory.CATALOG_SCORING,
        source_component="test.scoring",
        quarantine=dlq,
        suppress=True,
    ) as ctx:
        raise ValueError("Computation math domain error")

    assert ctx.has_error is True
    assert dlq.error_count == 1
    report = dlq.generate_report()
    assert report.quarantined_count == 1
    assert report.records[0].exception_message == "Computation math domain error"


def test_circuit_breaker_trips_on_consecutive_failures():
    cb = BatchCircuitBreaker(target_key="test_breaker", consecutive_failure_limit=3)

    assert not cb.is_tripped
    cb.record_failure()
    cb.record_failure()
    assert not cb.is_tripped
    cb.record_failure()
    assert cb.is_tripped

    import pytest

    with pytest.raises(CircuitBreakerTrippedError):
        cb.check_circuit()


def test_resilient_step_decorator():
    @resilient_step(
        category=ErrorCategory.DATABASE,
        source_component="test.step",
        fallback_value="fallback_result",
    )
    def risky_operation():
        raise RuntimeError("DB failed")

    result = risky_operation()
    assert result == "fallback_result"

