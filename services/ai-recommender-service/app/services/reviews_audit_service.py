"""Application service coordinating file-based review deduplication and gap reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.common.logger import get_logger
from app.domain.reviews.deduplication import (
    audit_and_deduplicate_payload,
    format_youtube_gap_tasks_md,
)

logger = get_logger("ai_recommender.services.reviews_audit")

DEFAULT_REVIEWS_IN = "cleaned_and_enriched_chassis_reviews_v6.json"
DEFAULT_RAW_REVIEWS_GLOB = "raw_chassis_reviews_*.json"
DEFAULT_CATALOG_IN = "unified_catalog_topsis_ready_v6.json"
DEFAULT_DEDUP_OUT = "reviews_deduplicated_v6.json"
DEFAULT_TASKS_MD_OUT = "youtube_gap_tasks.md"


class ReviewsAuditService:
    """Application orchestrator for persisted review deduplication and YouTube gap planning."""

    @staticmethod
    def _inspect_raw_reviews(raw_files: list[Path]) -> Dict[str, Any]:
        if not raw_files:
            return {"raw_file_found": None}
        raw_path = raw_files[0]
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        raw_laptops = raw_data.get("laptops", [])
        return {
            "raw_file_found": raw_path.name,
            "raw_entries": len(raw_laptops),
            "raw_editorial_total": sum(len(x.get("communities", {}).get("editorial", [])) for x in raw_laptops),
            "raw_discussions_total": sum(len(x.get("communities", {}).get("discussions", [])) for x in raw_laptops),
            "raw_real_yt_transcripts": sum(
                1
                for x in raw_laptops
                for v in x.get("youtube", {}).get("videos", [])
                if str(v.get("transcript_text") or "").strip()
            ),
        }

    def deduplicate_payload(
        self,
        reviews_data: Dict[str, Any],
        catalog_path: Optional[str] = None,
        *,
        include_unmatched_catalog: bool = False,
    ) -> Dict[str, Any]:
        """Run domain deduplication in memory, loading catalog JSON if present on disk."""
        catalog_data: Dict[str, Any] = {"laptops": []}
        resolved_catalog = catalog_path or DEFAULT_CATALOG_IN
        has_catalog = bool(resolved_catalog and Path(resolved_catalog).exists())
        if has_catalog:
            with open(resolved_catalog, "r", encoding="utf-8") as f:
                catalog_data = json.load(f)

        return audit_and_deduplicate_payload(
            reviews_data=reviews_data,
            catalog_data=catalog_data,
            catalog_source=resolved_catalog if has_catalog else "",
            include_unmatched_catalog=include_unmatched_catalog,
        )

    def run_audit_and_dedup(
        self,
        reviews_in: str = DEFAULT_REVIEWS_IN,
        catalog_in: str = DEFAULT_CATALOG_IN,
        dedup_out: str = DEFAULT_DEDUP_OUT,
        tasks_md_out: str = DEFAULT_TASKS_MD_OUT,
    ) -> Dict[str, Any]:
        """Load JSON inputs, run domain audit/dedup, and write Format B2 JSON + Markdown report."""
        with open(reviews_in, "r", encoding="utf-8") as f:
            rev_data = json.load(f)

        cat_data: Dict[str, Any] = {"laptops": []}
        if catalog_in and Path(catalog_in).exists():
            with open(catalog_in, "r", encoding="utf-8") as f:
                cat_data = json.load(f)

        raw_files = sorted(Path(".").glob(DEFAULT_RAW_REVIEWS_GLOB))
        raw_stats = self._inspect_raw_reviews(raw_files)

        output_payload = audit_and_deduplicate_payload(
            reviews_data=rev_data,
            catalog_data=cat_data,
            reviews_source=reviews_in,
            catalog_source=catalog_in,
            raw_stats=raw_stats,
        )

        dedup_path = Path(dedup_out)
        dedup_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dedup_path, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, indent=2, ensure_ascii=False)

        if tasks_md_out:
            tasks_path = Path(tasks_md_out)
            tasks_path.parent.mkdir(parents=True, exist_ok=True)
            tasks_md = format_youtube_gap_tasks_md(output_payload)
            tasks_path.write_text(tasks_md, encoding="utf-8")

        logger.info(
            "Saved deduplicated reviews to %s (%d unique chassis).",
            dedup_out,
            len(output_payload.get("chassis_reviews", [])),
        )
        return output_payload


def run_audit_and_dedup(
    reviews_in: str = DEFAULT_REVIEWS_IN,
    catalog_in: str = DEFAULT_CATALOG_IN,
    dedup_out: str = DEFAULT_DEDUP_OUT,
    tasks_md_out: str = DEFAULT_TASKS_MD_OUT,
) -> Dict[str, Any]:
    """Module-level convenience wrapper delegating to `ReviewsAuditService`."""
    return ReviewsAuditService().run_audit_and_dedup(
        reviews_in=reviews_in,
        catalog_in=catalog_in,
        dedup_out=dedup_out,
        tasks_md_out=tasks_md_out,
    )


__all__ = [
    "ReviewsAuditService",
    "run_audit_and_dedup",
]
