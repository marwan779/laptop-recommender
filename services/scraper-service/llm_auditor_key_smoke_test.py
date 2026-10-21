#!/usr/bin/env python3
"""Check every configured LLMAuditor endpoint through the project wrapper.

Run from the scraper-service directory with its virtual environment active.
Without --send-requests, this checks local configuration and wrapper wiring only.
With --send-requests, it makes one audit_batch call per configured endpoint with
an available key, using one synthetic laptop and SDK retries disabled.

The script never makes direct HTTP/SDK completion calls and never writes project
files. It masks API keys, and stops the whole run if a provider explicitly says
not to retry (for example Cloudflare Error 1010).
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import Any


class CaptureHandler(logging.Handler):
    """Capture LLMAuditor diagnostics, including its validated-success event."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def key_fragment(key: str) -> str:
    if len(key) > 12:
        return f"{key[:4]}…{key[-4:]}"
    if len(key) > 4:
        return f"{key[:2]}…{key[-2:]}"
    return "*" * len(key)


def safe_message(message: str, secret: str) -> str:
    return message.replace(secret, "[REDACTED]") if secret else message


def is_explicit_no_retry(records: list[logging.LogRecord]) -> bool:
    needles = (
        "browser_signature_banned",
        '"error_code":1010',
        '"error_code": 1010',
        "error 1010",
        "do not retry",
    )
    return any(
        needle in record.getMessage().lower()
        for record in records
        for needle in needles
    )


def run_endpoint(
    endpoint: Any,
    auditor_class: Any,
    process_env_before_import: dict[str, str],
    send_requests: bool,
) -> tuple[str, bool]:
    """Return (status, stop_all). Each instance has just one target endpoint."""
    api_key = os.getenv(endpoint.api_key_env, "")
    print(f"\n[{endpoint.name}] model={endpoint.model}")
    print(f"  Base URL: {endpoint.base_url}")
    print(f"  Credential variable: {endpoint.api_key_env}")

    if not api_key or not api_key.strip():
        print("  SKIP: credential is missing or empty; no wrapper request was made")
        return "SKIPPED", False
    if api_key != api_key.strip():
        print("  FAIL: credential has leading/trailing whitespace; no wrapper request was made")
        return "FAILED", False

    source = "process environment" if process_env_before_import.get(endpoint.api_key_env) else "dotenv/project environment"
    fingerprint = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
    print(f"  Credential: populated from {source}; masked={key_fragment(api_key)}; fingerprint={fingerprint}")

    try:
        # One endpoint per auditor prevents normal failover from masking which
        # provider answered. One wrapper retry is one completion attempt.
        auditor = auditor_class(endpoints=[endpoint], max_retries=1)
    except Exception as exc:
        print(f"  FAIL: LLMAuditor construction failed: {type(exc).__name__}: {safe_message(str(exc), api_key)}")
        return "FAILED", False

    active_names = [item.name for item in auditor.active_endpoints]
    if active_names != [endpoint.name]:
        print(f"  FAIL: active endpoints are {active_names!r}, not only {endpoint.name!r}; no request made")
        return "FAILED", False

    # This private client access is intentional: verify that LLMAuditor created
    # the endpoint client with the expected key, then disable SDK-level retries.
    client = auditor._clients.get(endpoint.name)
    if client is None:
        print("  FAIL: LLMAuditor did not create a client for this endpoint")
        return "FAILED", False
    if getattr(client, "api_key", None) != api_key:
        print("  FAIL: LLMAuditor's client key does not match the configured environment value")
        return "FAILED", False
    auditor._clients[endpoint.name] = client.with_options(max_retries=0)
    print("  Wrapper check: only this endpoint is active; SDK automatic retries disabled")

    if not send_requests:
        print("  CONFIG PASS: key is populated and attached to the isolated LLMAuditor client; no request sent")
        return "CONFIG_OK", False

    print("  Sending one synthetic-laptop audit through LLMAuditor.audit_batch")
    logger_names = ("llm_auditor", "pipeline.llm_auditor")
    capture = CaptureHandler()
    root_logger = logging.getLogger()
    old_root_level = root_logger.level
    root_logger.addHandler(capture)
    root_logger.setLevel(logging.DEBUG)
    named_loggers: list[tuple[logging.Logger, int]] = []
    for name in logger_names:
        logger = logging.getLogger(name)
        named_loggers.append((logger, logger.level))
        logger.setLevel(logging.DEBUG)

    result = None
    caught_error: Exception | None = None
    try:
        result = auditor.audit_batch(
            laptops=[{
                "title": "Synthetic smoke test; not a real product",
                "source_table": {"Memory": "16 GB"},
                "specs": {"memory": {"capacity_gb": 16}},
            }],
            identifiers=["llmauditor-smoke-test"],
        )
    except Exception as exc:
        caught_error = exc
    finally:
        root_logger.removeHandler(capture)
        root_logger.setLevel(old_root_level)
        for logger, old_level in named_loggers:
            logger.setLevel(old_level)

    relevant_records = [
        record for record in capture.records
        if record.name in logger_names or "Successfully audited batch via" in record.getMessage()
    ]
    for record in relevant_records:
        print(f"  [{record.levelname}] {safe_message(record.getMessage(), api_key)}")

    if is_explicit_no_retry(relevant_records):
        print("  STOP: provider explicitly said not to retry this base URL")
        return "BLOCKED_NO_RETRY", True

    if caught_error is not None:
        print(f"  FAIL: wrapper raised {type(caught_error).__name__}: {safe_message(str(caught_error), api_key)}")
        return "FAILED", False

    success_event = any(
        "Successfully audited batch via" in record.getMessage()
        and endpoint.name in record.getMessage()
        for record in relevant_records
    )
    if not success_event:
        print("  FAIL: no wrapper success event; the wrapper may have returned a synthetic result after failure")
        return "FAILED", False

    print("  PASS: nonempty provider response parsed and validated as BatchAuditResponse")
    result_items = getattr(result, "audited_laptops", []) or []
    result_ids = [str(getattr(item, "laptop_id", "")) for item in result_items]
    if len(result_ids) == 1 and result_ids[0] == "llmauditor-smoke-test":
        print("  PASS: response includes the expected synthetic laptop ID")
    elif not result_ids:
        print("  WARNING: response validated, but audited_laptops is empty")
    else:
        print(f"  WARNING: returned audit IDs {result_ids!r} do not match the submitted ID")
    return "PASSED", False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check all configured LLMAuditor endpoints through LLMAuditor.audit_batch."
    )
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="scraper-service directory (default: current directory)",
    )
    parser.add_argument(
        "--endpoint",
        action="append",
        help="test only this endpoint; repeat to select several. Default: every DEFAULT_ENDPOINTS entry.",
    )
    parser.add_argument(
        "--send-requests",
        "--send-request",
        dest="send_requests",
        action="store_true",
        help="send one live wrapper request per endpoint with a configured key; may consume quota",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    auditor_source = project_root / "pipeline" / "llm_auditor.py"
    if not auditor_source.is_file():
        print(f"FAIL: LLMAuditor source not found under {project_root}")
        return 2

    process_env_before_import = dict(os.environ)
    sys.dont_write_bytecode = True
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))

    try:
        from pipeline.llm_auditor import DEFAULT_ENDPOINTS, LLMAuditor
    except Exception as exc:
        print(f"FAIL: could not import LLMAuditor in this environment: {type(exc).__name__}: {exc}")
        return 2

    all_endpoints = list(DEFAULT_ENDPOINTS)
    if args.endpoint:
        requested = set(args.endpoint)
        known = {endpoint.name for endpoint in all_endpoints}
        unknown = sorted(requested - known)
        if unknown:
            print(f"FAIL: unknown endpoint name(s): {unknown}")
            print("Configured names: " + ", ".join(endpoint.name for endpoint in all_endpoints))
            return 2
        selected = [endpoint for endpoint in all_endpoints if endpoint.name in requested]
    else:
        selected = all_endpoints

    print(f"LLMAuditor endpoint check: {len(selected)} configured endpoint(s) selected")
    print("Mode: LIVE wrapper calls" if args.send_requests else "Mode: LOCAL CONFIGURATION ONLY; no API requests")
    if args.send_requests:
        print("Each configured endpoint with a key will receive one audit_batch call; retries are disabled.")
        print("An explicit 'Do not retry' block skips remaining models on that same base URL; other providers can still be tested.")

    counts: dict[str, int] = {}
    blocked_base_urls: set[str] = set()
    for endpoint in selected:
        if endpoint.base_url in blocked_base_urls:
            print(f"\n[{endpoint.name}] SKIP: {endpoint.base_url} already returned an explicit no-retry block")
            counts["BLOCKED_SKIPPED"] = counts.get("BLOCKED_SKIPPED", 0) + 1
            continue

        status, skip_base_url = run_endpoint(
            endpoint=endpoint,
            auditor_class=LLMAuditor,
            process_env_before_import=process_env_before_import,
            send_requests=args.send_requests,
        )
        counts[status] = counts.get(status, 0) + 1
        if skip_base_url:
            blocked_base_urls.add(endpoint.base_url)

    summary = ", ".join(f"{status}={count}" for status, count in counts.items())
    print(f"\nSummary: {summary or 'no endpoints checked'}")
    if counts.get("BLOCKED_NO_RETRY") or counts.get("BLOCKED_SKIPPED"):
        return 2
    if counts.get("FAILED"):
        return 1
    if args.send_requests and counts.get("SKIPPED"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
