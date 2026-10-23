"""Tests for the Global Microservice Resilience Framework.

Verifies:
  - ServiceErrorRecord schemas and status code extraction
  - DeadLetterQuarantine (DLQ) serialization and artifact saving
  - Dynamic BatchCircuitBreaker threshold evaluation (20% rate)
  - Resilient execution boundaries across microservice layers
"""

import json
from pathlib import Path

import pytest

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


class DummyNestedResponseError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)

        class Response:
            def __init__(self, code: int):
                self.status_code = code

        self.response = Response(status_code)


class DummyBotoClientError(Exception):
    def __init__(self, message: str, http_code: int):
        super().__init__(message)
        self.response = {"ResponseMetadata": {"HTTPStatusCode": http_code}}


def test_status_code_extraction():
    """Verify intelligent status code extraction across HTTP libraries."""
    assert extract_status_code(ValueError("Standard error")) is None
    assert extract_status_code(DummyHTTPError("Rate limited", 429)) == 429
    assert extract_status_code(DummyNestedResponseError("Forbidden", 403)) == 403
    assert extract_status_code(DummyBotoClientError("S3 Access Denied", 403)) == 403


def test_service_error_record_creation():
    """Verify ServiceErrorRecord model validation and fields."""
    record = ServiceErrorRecord(
        category=ErrorCategory.PIPELINE_EXTRACTION,
        severity=ErrorSeverity.ERROR,
        source_component="pipeline.deterministic",
        context={"url": "https://example.com/laptop", "item_idx": 95},
        exception_type="AttributeError",
        exception_message="'NoneType' object has no attribute 'get'",
        status_code=None,
        traceback="Traceback (most recent call last)...",
        recovery_action=RecoveryAction.QUARANTINED,
        payload_snapshot={"title": "Test Laptop", "price": 50000},
    )

    assert record.error_id is not None
    assert record.timestamp is not None
    assert record.category == ErrorCategory.PIPELINE_EXTRACTION
    assert record.payload_snapshot["title"] == "Test Laptop"
    assert record.status_code is None


def test_dead_letter_quarantine_collection_and_saving(tmp_path: Path):
    """Verify DLQ collects errors and persists JSON report."""
    dlq = DeadLetterQuarantine(target_key="elbadr", target_type="store")

    for i in range(3):
        dlq.mark_item_attempted()
        exc = ValueError(f"Corrupt spec row {i}")
        dlq.record_error(
            category=ErrorCategory.DOM_PARSING,
            source_component="store.elbadr",
            exception=exc,
            traceback_str="fake_tb",
            context={"url": f"https://elbadr.com/prod-{i}"},
            payload_snapshot={"id": i},
        )

    assert dlq.has_errors() is True
    assert dlq.error_count == 3

    report = dlq.export_report()
    assert report.target_key == "elbadr"
    assert report.quarantined_items_count == 3
    assert report.total_items_attempted == 3
    assert report.error_rate_pct == 100.0

    # Save to disk
    out_file = dlq.save_report(output_dir=tmp_path, target_key="elbadr")
    assert out_file is not None
    assert out_file.exists()

    with open(out_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["target_key"] == "elbadr"
    assert len(data["errors"]) == 3
    assert data["errors"][0]["context"]["url"] == "https://elbadr.com/prod-0"


def test_batch_circuit_breaker_threshold_trip():
    """Verify circuit breaker trips when failure rate exceeds 20% after minimum threshold."""
    cb = BatchCircuitBreaker(target_key="sigma", failure_threshold_pct=20.0, min_items_threshold=5)

    # 4 successes, 0 failures (0%) -> not tripped
    for _ in range(4):
        cb.record_success()
    assert cb.is_tripped is False

    # 1 failure (total 5 items, 1 failure = 20.0% -> at threshold, not strictly > 20%)
    tripped = cb.record_failure()
    assert tripped is False
    assert cb.is_tripped is False
    assert cb.failure_rate_pct == 20.0

    # Next failure: total 6 items, 2 failures = 33.3% > 20% -> trips
    tripped = cb.record_failure()
    assert tripped is True
    assert cb.is_tripped is True
    assert cb.failure_rate_pct > 20.0
    assert "exceeded safety threshold 20.0%" in (cb.tripped_reason or "")

    with pytest.raises(CircuitBreakerTrippedError):
        cb.check_circuit()


def test_batch_circuit_breaker_consecutive_failure_limit():
    """Verify circuit breaker trips immediately on reaching consecutive failure ceiling."""
    cb = BatchCircuitBreaker(
        target_key="twob",
        failure_threshold_pct=50.0,
        min_items_threshold=20,
        consecutive_failure_limit=5,
    )

    for i in range(4):
        cb.record_failure()
        assert cb.is_tripped is False

    # 5th consecutive failure trips regardless of min_items_threshold
    cb.record_failure()
    assert cb.is_tripped is True
    assert "Consecutive failure limit of 5 reached" in (cb.tripped_reason or "")


def test_resilient_boundary_item_isolation():
    """Verify resilient_boundary swallows item exception, logs it, and updates DLQ."""
    dlq = DeadLetterQuarantine(target_key="compumarts")
    cb = BatchCircuitBreaker(target_key="compumarts", failure_threshold_pct=50.0)

    # Simulate loop over products where item 2 crashes
    processed_items = []
    for idx in range(3):
        with resilient_boundary(
            category=ErrorCategory.PIPELINE_EXTRACTION,
            source_component="pipeline.deterministic",
            context={"item_idx": idx},
            quarantine=dlq,
            circuit_breaker=cb,
            payload_snapshot={"idx": idx},
            suppress=True,
        ) as b_ctx:
            if idx == 1:
                # Simulate the item 95 incident
                raise KeyError("CANONICAL_FAMILIES")
            processed_items.append(idx)

    # Items 0 and 2 succeeded; item 1 was isolated and quarantined
    assert processed_items == [0, 2]
    assert dlq.error_count == 1
    err = dlq.get_errors()[0]
    assert err.exception_type == "KeyError"
    assert err.context["item_idx"] == 1
    assert err.recovery_action == RecoveryAction.QUARANTINED
    assert cb.stats()["success_count"] == 2
    assert cb.stats()["failure_count"] == 1


def test_resilient_boundary_reraises_when_suppress_false():
    """Verify resilient_boundary re-raises exception when suppress=False."""
    dlq = DeadLetterQuarantine(target_key="storage_test")

    with (
        pytest.raises(PermissionError),
        resilient_boundary(
            category=ErrorCategory.STORAGE,
            source_component="storage.local",
            quarantine=dlq,
            suppress=False,
        ),
    ):
        raise PermissionError("Access denied to write file")

    assert dlq.error_count == 1
    assert dlq.get_errors()[0].exception_type == "PermissionError"


def test_resilient_step_decorator():
    """Verify resilient_step decorator catches errors and returns fallback."""

    @resilient_step(
        category=ErrorCategory.NOTIFICATION,
        source_component="email.service",
        fallback_value=False,
    )
    def send_flaky_email(recipient: str):
        if recipient == "bad@example.com":
            raise ConnectionError("SMTP Server down")
        return True

    assert send_flaky_email("good@example.com") is True
    assert send_flaky_email("bad@example.com") is False


from unittest.mock import patch
from app.pipeline.catalog_pipeline import GenericCatalogPipeline
from app.schemas.laptop import RetailerProduct


def test_pipeline_process_catalog_quarantines_poison_pill_and_saves_dlq(tmp_path: Path):
    """Verify that a poison-pill exception inside process_catalog is quarantined into DLQ and does not abort the run."""
    pipeline = GenericCatalogPipeline(no_audit=True)

    products = [
        RetailerProduct(
            store_name="El Badr Group",
            store_key="elbadr",
            store_domain="elbadrgroupeg.store",
            title=f"Lenovo Legion Pro 5 Laptop #{i} Core i7 16GB RTX 4060",
            product_url=f"https://elbadrgroupeg.store/laptop-{i}",
            price_egp=60000.0,
            specs={"Processor": "Intel Core i7-13700HX", "Memory": "16GB DDR5"},
        )
        for i in range(1, 11)
    ]

    ckpt_file = tmp_path / "checkpoint.jsonl"

    original_process = pipeline.pipeline.process_raw_product

    def faulty_process(raw_prod):
        if "Laptop #5" in raw_prod.title:
            # Simulate the item 95/97 incident
            raise AttributeError("'NoneType' object has no attribute 'CANONICAL_FAMILIES'")
        return original_process(raw_prod)

    with patch.object(pipeline.pipeline, "process_raw_product", side_effect=faulty_process):
        results = pipeline.process_catalog(
            products=products,
            store_key="elbadr",
            checkpoint_file=ckpt_file,
            failure_threshold_pct=20.0,
        )

    # 9 products succeeded, 1 was quarantined
    assert len(results) == 9
    assert pipeline.last_quarantine is not None
    assert pipeline.last_quarantine.error_count == 1
    assert pipeline.last_circuit_breaker is not None
    assert pipeline.last_circuit_breaker.is_tripped is False

    err = pipeline.last_quarantine.get_errors()[0]
    assert err.exception_type == "AttributeError"
    assert "CANONICAL_FAMILIES" in err.exception_message
    assert "Laptop #5" in err.context["title"]

    # DLQ JSON artifact verified
    assert pipeline.last_quarantine_file is not None
    q_path = Path(pipeline.last_quarantine_file)
    assert q_path.exists()

    with open(q_path, encoding="utf-8") as f:
        dlq_data = json.load(f)

    assert dlq_data["target_key"] == "elbadr"
    assert dlq_data["quarantined_items_count"] == 1
    assert dlq_data["error_rate_pct"] == 10.0
    assert len(dlq_data["errors"]) == 1
    assert dlq_data["errors"][0]["payload_snapshot"]["title"] == "Lenovo Legion Pro 5 Laptop #5 Core i7 16GB RTX 4060"


def test_pipeline_process_catalog_circuit_breaker_trip(tmp_path: Path):
    """Verify that when the failure rate exceeds 20%, process_catalog halts early."""
    pipeline = GenericCatalogPipeline(no_audit=True)

    products = [
        RetailerProduct(
            store_name="Sigma Computer",
            store_key="sigma",
            store_domain="sigma-computer.com",
            title=f"Laptop #{i} Core i7 16GB",
            product_url=f"https://sigma-computer.com/laptop-{i}",
            price_egp=50000.0,
            specs={"Processor": "Intel Core i7-13700HX"},
        )
        for i in range(1, 11)
    ]

    def frequent_failure(raw_prod):
        # Fail items 1, 2, 3 -> trips consecutive or rate threshold
        if any(f"Laptop #{i}" in raw_prod.title for i in (1, 2, 3)):
            raise RuntimeError("Corrupted HTML table")
        return pipeline.pipeline.process_raw_product(raw_prod)

    with patch.object(pipeline.pipeline, "process_raw_product", side_effect=frequent_failure):
        results = pipeline.process_catalog(
            products=products,
            store_key="sigma",
            checkpoint_file=tmp_path / "sigma_ckpt.jsonl",
            failure_threshold_pct=20.0,
        )

    # Circuit breaker tripped early, halting before all 10 items were evaluated
    assert pipeline.last_circuit_breaker is not None
    assert pipeline.last_circuit_breaker.is_tripped is True
    assert len(results) < 10
