"""Dead-Letter Quarantine (DLQ) Subsystem."""

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

    def __init__(self, target_key: str = "global", target_type: str = "catalog") -> None:
        self.target_key = target_key
        self.target_type = target_type
        self._errors: list[ServiceErrorRecord] = []
        self._lock = Lock()
        self._total_attempted = 0
        self._circuit_broken = False

    def mark_item_attempted(self) -> None:
        with self._lock:
            self._total_attempted += 1

    def mark_circuit_broken(self) -> None:
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
            "Quarantined failure in '%s' (ErrorID: %s, Category: %s): %s",
            source_component,
            record.error_id,
            category.value,
            record.exception_message,
        )
        return record

    @property
    def error_count(self) -> int:
        with self._lock:
            return len(self._errors)

    @property
    def total_attempted(self) -> int:
        with self._lock:
            return self._total_attempted

    def generate_report(self) -> DeadLetterQuarantineReport:
        with self._lock:
            cat_counts: dict[str, int] = {}
            sev_counts: dict[str, int] = {}

            for err in self._errors:
                cat_counts[err.category.value] = cat_counts.get(err.category.value, 0) + 1
                sev_counts[err.severity.value] = sev_counts.get(err.severity.value, 0) + 1

            return DeadLetterQuarantineReport(
                target_key=self.target_key,
                target_type=self.target_type,
                total_attempted=self._total_attempted,
                quarantined_count=len(self._errors),
                circuit_broken=self._circuit_broken,
                errors_by_category=cat_counts,
                errors_by_severity=sev_counts,
                records=list(self._errors),
            )

    def save_artifact(self, output_dir: Path | str) -> Path | None:
        report = self.generate_report()
        if report.quarantined_count == 0:
            return None

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        timestamp_slug = utcnow_str().replace(":", "-").replace(".", "-")
        filename = f"dlq_{self.target_key}_{timestamp_slug}.json"
        dest = out_path / filename

        with dest.open("w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)

        logger.info("Saved Dead-Letter Quarantine artifact to: %s", dest)
        return dest

