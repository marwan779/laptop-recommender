"""Dead-Letter Quarantine (DLQ) Subsystem.

Collects, organizes, and serializes failed items and exceptions into
diagnostic quarantine artifacts for offline inspection and replay.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

from app.common.resilience.models import (
    DeadLetterQuarantineReport,
    ErrorCategory,
    ErrorSeverity,
    RecoveryAction,
    ServiceErrorRecord,
    utcnow_str,
)

logger = logging.getLogger(__name__)


class DeadLetterQuarantine:
    """Thread-safe collector for quarantined failures across microservice tasks."""

    def __init__(self, target_key: str = "global", target_type: str = "store") -> None:
        self.target_key = target_key
        self.target_type = target_type
        self._errors: list[ServiceErrorRecord] = []
        self._lock = Lock()
        self._total_attempted = 0
        self._circuit_broken = False

    def mark_item_attempted(self) -> None:
        """Register an item execution attempt."""
        with self._lock:
            self._total_attempted += 1

    def mark_circuit_broken(self) -> None:
        """Record that the enclosing batch was aborted by the circuit breaker."""
        with self._lock:
            self._circuit_broken = True

    def record_error(
        self,
        category: ErrorCategory,
        source_component: str,
        exception: BaseException,
        traceback_str: str,
        context: dict[str, Any] | None = None,
        status_code: int | None = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        recovery_action: RecoveryAction = RecoveryAction.QUARANTINED,
        payload_snapshot: dict[str, Any] | None = None,
    ) -> ServiceErrorRecord:
        """Create and store a ServiceErrorRecord in the quarantine buffer."""
        record = ServiceErrorRecord(
            category=category,
            severity=severity,
            source_component=source_component,
            context=context or {},
            exception_type=type(exception).__name__,
            exception_message=str(exception),
            status_code=status_code,
            traceback=traceback_str,
            recovery_action=recovery_action,
            payload_snapshot=payload_snapshot,
        )

        with self._lock:
            self._errors.append(record)

        logger.warning(
            "[DLQ Quarantine] Isolated %s in '%s' (%s): %s [status=%s, id=%s]",
            record.category.value,
            record.source_component,
            record.exception_type,
            record.exception_message,
            record.status_code,
            record.error_id,
        )
        return record

    def add_record(self, record: ServiceErrorRecord) -> None:
        """Add an already constructed ServiceErrorRecord."""
        with self._lock:
            self._errors.append(record)

    def has_errors(self) -> bool:
        """Return True if any errors have been quarantined."""
        with self._lock:
            return len(self._errors) > 0

    @property
    def error_count(self) -> int:
        """Total number of errors quarantined."""
        with self._lock:
            return len(self._errors)

    def get_errors(self) -> list[ServiceErrorRecord]:
        """Return a copy of all quarantined error records."""
        with self._lock:
            return list(self._errors)

    def export_report(self, total_items_attempted: int | None = None) -> DeadLetterQuarantineReport:
        """Compile quarantined items into a structured DeadLetterQuarantineReport."""
        with self._lock:
            total = total_items_attempted if total_items_attempted is not None else self._total_attempted
            total = max(total, len(self._errors))
            error_count = len(self._errors)
            error_rate = (error_count / total * 100.0) if total > 0 else 0.0

            return DeadLetterQuarantineReport(
                target_key=self.target_key,
                target_type=self.target_type,
                total_items_attempted=total,
                quarantined_items_count=error_count,
                error_rate_pct=round(error_rate, 2),
                circuit_broken=self._circuit_broken,
                errors=list(self._errors),
            )

    def save_report(
        self,
        output_dir: Path | str,
        target_key: str | None = None,
        filename: str | None = None,
    ) -> Path | None:
        """Persist the quarantine report to disk as JSON.

        Returns the Path to the written file, or None if no errors exist to quarantine.
        """
        with self._lock:
            if not self._errors:
                return None

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        key = target_key or self.target_key
        if not filename:
            # Timestamp formatted with safe characters for all operating systems
            safe_ts = utcnow_str().replace(":", "-").replace(".", "-")
            filename = f"{key}_{safe_ts}_quarantine.json"

        filepath = out_path / filename
        report = self.export_report()

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)

        logger.info(
            "[DLQ Quarantine] Saved %d quarantined error records to '%s'",
            len(report.errors),
            filepath.resolve(),
        )
        return filepath
