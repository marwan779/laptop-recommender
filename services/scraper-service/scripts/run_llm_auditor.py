"""CLI Runner for Post-Pipeline Ground-Truth LLM Auditor.

Audits catalog JSON results against raw scraped specifications using Google Gemini API.
Detects contradictions, applies verified corrections through PhysicalValidator,
and produces detailed markdown audit reports and JSONL traces.

Usage:
    # Dry-run audit on the 4 targeted test cases:
    python scripts/run_llm_auditor.py --cases "lenovo-yoga-7,asus-vivobook-16,hp-victus-15,msi-thin-15"

    # Apply corrections to the 4 targeted test cases:
    python scripts/run_llm_auditor.py --cases "lenovo-yoga-7,asus-vivobook-16,hp-victus-15,msi-thin-15" --apply

    # Dry-run audit on first 10 laptops:
    python scripts/run_llm_auditor.py --limit 10

    # Full catalog audit and patch (with automatic .bak backup):
    python scripts/run_llm_auditor.py --apply
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.llm_auditor import GeminiAuditor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_llm_auditor")


def generate_markdown_report(
    corrections_log: List[Dict[str, Any]],
    total_audited: int,
    laptops_with_issues: int,
    output_path: Path,
    applied: bool,
    model_name: str,
) -> None:
    """Generate a GitHub-flavored Markdown audit report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    mode_str = "APPLIED & SAVED" if applied else "DRY-RUN (NO CHANGES SAVED)"

    # Count by field
    field_counts: Dict[str, int] = {}
    for entry in corrections_log:
        f = entry.get("field_path", "unknown")
        field_counts[f] = field_counts.get(f, 0) + 1

    lines = [
        "# Post-Pipeline Ground-Truth LLM Audit Report",
        "",
        f"- **Timestamp**: `{timestamp}`",
        f"- **Auditor Engine**: Google Gemini (`{model_name}`)",
        f"- **Audit Mode**: `{mode_str}`",
        f"- **Total Laptops Audited**: {total_audited}",
        f"- **Laptops with Contradictions Detected**: {laptops_with_issues} ({round(laptops_with_issues / max(1, total_audited) * 100, 1)}%)",
        f"- **Total Field Corrections**: {len(corrections_log)}",
        "",
        "## Summary by Field",
        "",
        "| Field Path | Corrections Count |",
        "| :--- | :--- |",
    ]

    for f, count in sorted(field_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| `{f}` | {count} |")

    lines.extend([
        "",
        "## Itemized Corrections Ledger",
        "",
    ])

    if not corrections_log:
        lines.append("> [!NOTE]\n> Zero contradictions detected. All audited laptop specifications strictly match raw ground truth!")
    else:
        for idx, item in enumerate(corrections_log, start=1):
            title = item.get("title", "Unknown Laptop")
            url = item.get("url", "")
            fpath = item.get("field_path", "")
            old_val = item.get("old_value")
            new_val = item.get("new_value")
            evidence = item.get("evidence_quote", "").replace("\n", " ").strip()
            reason = item.get("reason", "").replace("\n", " ").strip()

            lines.append(f"### {idx}. {title}")
            lines.append(f"- **URL**: [{url}]({url})")
            lines.append(f"- **Field**: `{fpath}`")
            lines.append(f"- **Catalog Value**: `{json.dumps(old_val)}`")
            lines.append(f"- **Corrected Value**: `{json.dumps(new_val)}`")
            lines.append(f"- **Raw Spec Evidence**: *\"{evidence}\"*")
            lines.append(f"- **Technical Rationale**: {reason}")
            lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    logger.info("Saved Markdown audit report to %s", output_path)


def save_jsonl_trace(corrections_log: List[Dict[str, Any]], trace_path: Path) -> None:
    """Save machine-readable JSONL audit trace."""
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with open(trace_path, "w", encoding="utf-8") as f:
        for record in corrections_log:
            record_copy = dict(record)
            record_copy["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            f.write(json.dumps(record_copy, ensure_ascii=False) + "\n")
    logger.info("Saved JSONL audit trace to %s (%d records)", trace_path, len(corrections_log))


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-Pipeline Ground-Truth LLM Auditor")
    parser.add_argument(
        "--input",
        type=str,
        default="pipeline_results_compumarts.json",
        help="Path to input catalog JSON file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to output catalog JSON file (defaults to --input)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply corrections directly to the output JSON file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Perform dry-run audit without modifying catalog files",
    )
    parser.add_argument(
        "--cases",
        type=str,
        default=None,
        help="Comma-separated list of URL substrings or indices to target (e.g. 'yoga-7,vivobook-16')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit audit to first N laptops",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Number of laptops per Gemini request (default: 4)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-flash-latest",
        help="Gemini model name (default: gemini-flash-latest)",
    )
    parser.add_argument(
        "--fallback-models",
        type=str,
        default="gemini-3.8-flash,gemini-flash-lite-latest",
        help="Comma-separated Gemini fallback model names (default: 'gemini-3.8-flash,gemini-flash-lite-latest')",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Google Gemini API key (defaults to GEMINI_API_KEY environment variable)",
    )
    parser.add_argument(
        "--report",
        type=str,
        default="scratch/audit_report_gemini.md",
        help="Path to markdown audit report output",
    )
    parser.add_argument(
        "--trace",
        type=str,
        default="scratch/audit_corrections.jsonl",
        help="Path to jsonl audit trace output",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        default=False,
        help="Disable automatic .bak backup creation before saving",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input file does not exist: %s", input_path)
        sys.exit(1)

    output_path = Path(args.output or args.input)

    # Determine execution mode
    should_apply = args.apply and not args.dry_run

    # Load catalog
    logger.info("Loading catalog from %s...", input_path)
    with open(input_path, "r", encoding="utf-8") as f:
        catalog: List[Dict[str, Any]] = json.load(f)
    logger.info("Loaded %d laptops from catalog.", len(catalog))

    # Target specific cases if requested
    items_to_audit = catalog
    index_mapping: List[int] = list(range(len(catalog)))

    if args.cases:
        target_patterns = [c.strip().lower() for c in args.cases.split(",") if c.strip()]
        matched_items = []
        matched_indices = []
        for idx, lap in enumerate(catalog):
            url = (lap.get("url") or "").lower()
            title = (lap.get("title") or "").lower()
            idx_str = str(idx)
            if any(p in url or p in title or p == idx_str for p in target_patterns):
                matched_items.append(lap)
                matched_indices.append(idx)
        items_to_audit = matched_items
        index_mapping = matched_indices
        logger.info(
            "Filtered catalog using --cases patterns (%s): %d laptops matched (indices: %s).",
            args.cases, len(items_to_audit), matched_indices
        )

    if args.limit:
        items_to_audit = items_to_audit[:args.limit]
        index_mapping = index_mapping[:args.limit]
        logger.info("Limited audit to first %d laptops.", len(items_to_audit))

    if not items_to_audit:
        logger.warning("No laptops found to audit. Exiting.")
        return

    # Initialize GeminiAuditor
    try:
        fallback_list = [m.strip() for m in args.fallback_models.split(",") if m.strip()]
        auditor = GeminiAuditor(
            api_key=args.api_key,
            model=args.model,
            fallback_models=fallback_list,
        )
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(
        "Starting Ground-Truth LLM Audit (total: %d laptops, batch_size: %d, model: %s, mode: %s)...",
        len(items_to_audit), args.batch_size, args.model, "APPLY" if should_apply else "DRY-RUN"
    )

    def progress_callback(processed: int, total: int, corrections_count: int) -> None:
        logger.info("Progress: %d/%d laptops audited | Contradictions detected: %d", processed, total, corrections_count)

    # Execute audit
    updated_items, corrections_log = auditor.audit_catalog(
        catalog=items_to_audit,
        batch_size=args.batch_size,
        apply_patches=should_apply,
        progress_callback=progress_callback,
    )

    # Remap laptop_index in log to catalog index
    unique_laptops_with_issues = set()
    for entry in corrections_log:
        local_idx = entry.get("laptop_index", 0)
        if local_idx < len(index_mapping):
            entry["laptop_index"] = index_mapping[local_idx]
        unique_laptops_with_issues.add(entry.get("laptop_index"))

    logger.info("=" * 80)
    logger.info("AUDIT SUMMARY:")
    logger.info("  Total Laptops Audited:        %d", len(items_to_audit))
    logger.info("  Laptops with Contradictions:  %d", len(unique_laptops_with_issues))
    logger.info("  Total Field Corrections:      %d", len(corrections_log))
    logger.info("=" * 80)

    # If applying patches, write back to catalog
    if should_apply and corrections_log:
        # Create backup
        if not args.no_backup and output_path.exists():
            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = output_path.with_suffix(f".{timestamp_str}.bak")
            shutil.copy2(output_path, backup_path)
            logger.info("Created backup of original catalog at: %s", backup_path)

        # Merge updated items back into catalog
        for idx, updated_laptop in zip(index_mapping, updated_items):
            catalog[idx] = updated_laptop

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        logger.info("Successfully wrote updated catalog to: %s", output_path)

    # Generate Markdown and JSONL reports
    report_path = Path(args.report)
    trace_path = Path(args.trace)
    generate_markdown_report(
        corrections_log=corrections_log,
        total_audited=len(items_to_audit),
        laptops_with_issues=len(unique_laptops_with_issues),
        output_path=report_path,
        applied=should_apply,
        model_name=args.model,
    )
    save_jsonl_trace(corrections_log, trace_path)


if __name__ == "__main__":
    main()

