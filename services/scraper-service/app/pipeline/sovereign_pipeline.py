"""Isolated small-batch extraction pipeline powered by SovereignEG dual-source reconciliation.

Pipeline B runs when the post-Level-1 store batch size is at or below
``LLM_FULL_EXTRACT_BATCH_THRESHOLD``. It never loads NuExtract/GLiNER ONNX models
and never mutates ``icecat_specs_cache.json``'s ``llm_cache`` entries used by
Pipeline A.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.common.logger import get_logger
from app.core.sovereign_config import SovereignConfig
from app.domain.catalog.sovereign_prompt import (
    build_batch_messages,
    build_dual_source_payload,
    build_messages,
    extract_batch_results,
    validate_and_normalize_extracted_specs,
)
from app.infrastructure.sovereigneg_client import CallTelemetry, SovereignEGClient
from app.matching.combiner import CatalogCombiner
from app.matching.models import CanonicalLaptop, UnifiedCatalog
from app.pipeline.catalog_pipeline import GenericCatalogPipeline
from app.pipeline.icecat.enricher import IcecatCatalogEnricher

logger = get_logger("pipeline.sovereign")

DEFAULT_SOVEREIGN_CACHE_FILENAME = "sovereign_extract_cache.json"


@dataclass
class SovereignRunSummary:
    """Observability counters for one Pipeline B execution."""

    total_laptops: int = 0
    cache_hits: int = 0
    llm_extracted: int = 0
    fallback_count: int = 0
    primary_key_calls: int = 0
    fallback_key_calls: int = 0
    primary_key_exhausted: bool = False
    fallback_key_exhausted: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    models_used: dict[str, int] = field(default_factory=dict)


def _compute_input_hash(
    laptop: CanonicalLaptop,
    icecat_specs: dict[str, Any] | None,
    primary_model: str,
) -> str:
    """Deterministic fingerprint for caching Pipeline B extractions cleanly."""
    payload = {
        "canonical_id": laptop.canonical_id,
        "mpn": laptop.mpn,
        "title": laptop.title,
        "raw_store_context": laptop.raw_store_context,
        "icecat_mpn": laptop.icecat_mpn,
        "icecat_match_type": laptop.icecat_match_type,
        "has_icecat_specs": bool(icecat_specs),
        "primary_model": primary_model,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _resolve_verification_status(icecat_match_type: str | None, llm_ok: bool) -> str:
    if icecat_match_type == "EXACT_MATCH":
        return "VERIFIED_ICECAT"
    if icecat_match_type == "VARIANT_MATCH":
        return "VERIFIED_ICECAT_VARIANT"
    return "LLM_EXTRACTED" if llm_ok else "NOT_FOUND"


class SovereignSmallBatchPipeline:
    """Isolated Pipeline B: Sanitizer -> Combiner -> Read-only Icecat -> SovereignEG -> Validator."""

    def __init__(
        self,
        config: SovereignConfig | None = None,
        client: SovereignEGClient | None = None,
        icecat_enricher: IcecatCatalogEnricher | None = None,
        cache_path: Path | str | None = None,
        allow_live_icecat_search: bool = True,
    ) -> None:
        self.config = config or SovereignConfig.from_env()
        self.client = client or SovereignEGClient(config=self.config)
        self._icecat_enricher = icecat_enricher
        self.cache_path = Path(cache_path) if cache_path else None
        self.allow_live_icecat_search = allow_live_icecat_search
        self.last_summary = SovereignRunSummary()

    # ── cache helpers ───────────────────────────────────────────────────

    @staticmethod
    def _load_cache(path: Path | None) -> dict[str, dict[str, Any]]:
        if path is None or not path.is_file():
            return {}
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("[SovereignPipeline] Could not load cache '%s': %s", path, exc)
            return {}

    @staticmethod
    def _save_cache(path: Path | None, cache: dict[str, dict[str, Any]]) -> None:
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(cache, handle, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.warning("[SovereignPipeline] Could not persist cache '%s': %s", path, exc)

    # ── extraction helpers ──────────────────────────────────────────────

    def _extract_single(
        self,
        laptop: CanonicalLaptop,
        icecat_specs: dict[str, Any] | None,
    ) -> tuple[dict[str, Any] | None, CallTelemetry]:
        payload = build_dual_source_payload(laptop, icecat_specs)
        messages = build_messages(payload)
        parsed, telemetry = self.client.complete_json(messages)
        if parsed is None:
            return None, telemetry
        # Support either bare 12-category dict or wrapped {"results": {cid: ...}}
        extracted = extract_batch_results(parsed, [laptop.canonical_id])
        return extracted.get(laptop.canonical_id, parsed), telemetry

    def _extract_micro_batch(
        self,
        batch: list[tuple[CanonicalLaptop, dict[str, Any] | None]],
    ) -> tuple[dict[str, dict[str, Any] | None], list[CallTelemetry]]:
        telemetries: list[CallTelemetry] = []
        if len(batch) == 1:
            lap, ice = batch[0]
            extracted, tel = self._extract_single(lap, ice)
            telemetries.append(tel)
            return {lap.canonical_id: extracted}, telemetries

        payloads = [build_dual_source_payload(lap, ice) for lap, ice in batch]
        expected_ids = [lap.canonical_id for lap, _ in batch]
        parsed, tel = self.client.complete_json(build_batch_messages(payloads))
        telemetries.append(tel)

        matched = extract_batch_results(parsed, expected_ids)
        out: dict[str, dict[str, Any] | None] = {}
        for lap, ice in batch:
            cid = lap.canonical_id
            if cid in matched:
                out[cid] = matched[cid]
            else:
                # Fall back to single-item extraction only for missing entries in the micro-batch
                single_res, single_tel = self._extract_single(lap, ice)
                telemetries.append(single_tel)
                out[cid] = single_res
        return out, telemetries

    def _lookup_icecat_readonly(
        self,
        catalog: UnifiedCatalog,
        out_dir: Path,
    ) -> tuple[IcecatCatalogEnricher, dict[str, dict[str, Any] | None]]:
        enricher = self._icecat_enricher or IcecatCatalogEnricher(
            cache_path=out_dir / "icecat_specs_cache.json",
            match_report_path=out_dir / "icecat_match_report.json",
            run_llm_fallback=False,
            enable_web_search=False,
        )

        icecat_by_cid: dict[str, dict[str, Any] | None] = {}
        total = len(catalog.laptops)
        cache_dirty = False

        for idx, laptop in enumerate(catalog.laptops, 1):
            cid = laptop.canonical_id
            match_info = enricher.matches_cache.get(cid)
            if not match_info and self.allow_live_icecat_search:
                logger.info("[SovereignPipeline %d/%d] Read-only Icecat lookup for %s...", idx, total, cid)
                match_info = enricher.search_service.match_laptop(laptop.model_dump())
                if match_info.get("match_status") in ("EXACT_MATCH", "VARIANT_MATCH"):
                    enricher.matches_cache[cid] = match_info
                    cache_dirty = True

            status = (match_info or {}).get("match_status") or "NOT_FOUND"
            icecat_id = (match_info or {}).get("icecat_product_id")
            laptop.icecat_match_type = status
            laptop.icecat_product_id = icecat_id
            laptop.icecat_mpn = (match_info or {}).get("icecat_mpn")
            laptop.icecat_url = (match_info or {}).get("icecat_url")

            ice_specs: dict[str, Any] | None = None
            if status in ("EXACT_MATCH", "VARIANT_MATCH") and icecat_id:
                ice_specs = enricher.get_or_fetch_icecat_specs(icecat_id)
                if ice_specs:
                    cache_dirty = True
                else:
                    laptop.icecat_match_type = "NOT_FOUND"
            else:
                laptop.icecat_match_type = "NOT_FOUND"

            icecat_by_cid[cid] = ice_specs

        if cache_dirty:
            enricher._save_caches()
        return enricher, icecat_by_cid

    # ── public entry point ──────────────────────────────────────────────

    def run_lightweight_store_pipeline(
        self,
        products: list[Any],
        store_key: str,
        checkpoint_file: Path | None = None,
    ) -> tuple[list[dict[str, Any]], GenericCatalogPipeline]:
        """Run sanitizer + lightweight deterministic extraction with NO ONNX models."""
        pipeline = GenericCatalogPipeline(
            ai_fallback=None,
            no_audit=True,
            core_only_ai=True,
        )
        structured = pipeline.process_catalog(
            products=products,
            store_key=store_key,
            checkpoint_file=checkpoint_file,
        )
        return structured, pipeline

    def enrich_unified_catalog(
        self,
        catalog: UnifiedCatalog,
        out_dir: Path,
    ) -> UnifiedCatalog:
        """Enrich a combined UnifiedCatalog via read-only Icecat + SovereignEG micro-batches."""
        summary = SovereignRunSummary(total_laptops=len(catalog.laptops))
        if not catalog.laptops:
            self.last_summary = summary
            return catalog

        resolved_cache_path = self.cache_path or (out_dir / DEFAULT_SOVEREIGN_CACHE_FILENAME)
        cache = self._load_cache(resolved_cache_path)

        enricher, icecat_by_cid = self._lookup_icecat_readonly(catalog, out_dir)

        pending: list[tuple[CanonicalLaptop, dict[str, Any] | None, str]] = []
        for laptop in catalog.laptops:
            ice_specs = icecat_by_cid.get(laptop.canonical_id)
            in_hash = _compute_input_hash(laptop, ice_specs, self.config.primary_model)
            cached = cache.get(laptop.canonical_id)
            if (
                isinstance(cached, dict)
                and cached.get("input_hash") == in_hash
                and isinstance(cached.get("specs"), dict)
            ):
                laptop.specs = validate_and_normalize_extracted_specs(
                    cached["specs"],
                    deterministic_specs=laptop.specs,
                    title=laptop.title,
                    icecat_specs=ice_specs,
                )
                laptop.verification_status = _resolve_verification_status(laptop.icecat_match_type, llm_ok=True)
                summary.cache_hits += 1
            else:
                pending.append((laptop, ice_specs, in_hash))

        extracted_map: dict[str, dict[str, Any] | None] = {}
        if pending:
            step = max(1, self.config.micro_batch_size)
            batches = [[(lap, ice) for lap, ice, _ in pending[i : i + step]] for i in range(0, len(pending), step)]
            max_workers = min(len(batches), max(1, self.config.max_concurrency))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._extract_micro_batch, batch) for batch in batches]
                for fut in as_completed(futures):
                    batch_out, batch_telemetries = fut.result()
                    extracted_map.update(batch_out)
                    for tel in batch_telemetries:
                        summary.prompt_tokens += tel.prompt_tokens
                        summary.completion_tokens += tel.completion_tokens
                        if tel.key_slot_used == "primary":
                            summary.primary_key_calls += 1
                        elif tel.key_slot_used == "fallback":
                            summary.fallback_key_calls += 1
                        if tel.model_used:
                            summary.models_used[tel.model_used] = summary.models_used.get(tel.model_used, 0) + 1
                        summary.primary_key_exhausted = summary.primary_key_exhausted or tel.primary_key_exhausted
                        summary.fallback_key_exhausted = summary.fallback_key_exhausted or tel.fallback_key_exhausted

        cache_dirty = False
        for laptop, ice_specs, in_hash in pending:
            raw_extracted = extracted_map.get(laptop.canonical_id)
            if raw_extracted is not None:
                laptop.specs = validate_and_normalize_extracted_specs(
                    raw_extracted,
                    deterministic_specs=laptop.specs,
                    title=laptop.title,
                    icecat_specs=ice_specs,
                )
                laptop.verification_status = _resolve_verification_status(laptop.icecat_match_type, llm_ok=True)
                cache[laptop.canonical_id] = {
                    "input_hash": in_hash,
                    "specs": deepcopy(laptop.specs),
                }
                cache_dirty = True
                summary.llm_extracted += 1
            else:
                # Per-laptop fail-safe: apply deterministic + Icecat merge ONLY for this failed laptop
                if ice_specs and laptop.icecat_match_type in ("EXACT_MATCH", "VARIANT_MATCH"):
                    enricher.apply_icecat_specs_to_laptop(laptop, ice_specs, laptop.icecat_match_type)
                    enricher.finalize_laptop_specs(laptop, ice_specs)
                    laptop.verification_status = _resolve_verification_status(laptop.icecat_match_type, llm_ok=False)
                else:
                    enricher.finalize_laptop_specs(laptop, None)
                    laptop.verification_status = "NOT_FOUND"
                summary.fallback_count += 1

        if cache_dirty:
            self._save_cache(resolved_cache_path, cache)

        if summary.primary_key_exhausted:
            logger.warning(
                "[SovereignPipeline] ALERT: ENRICHER_LLM_API_KEY ran out of credits/quota during run "
                "(primary_calls=%d, fallback_calls=%d).",
                summary.primary_key_calls,
                summary.fallback_key_calls,
            )

        logger.info(
            "[SovereignPipeline] Complete: total=%d | cache_hits=%d | llm_extracted=%d | fallback=%d | "
            "primary_calls=%d | fallback_calls=%d | models=%s",
            summary.total_laptops,
            summary.cache_hits,
            summary.llm_extracted,
            summary.fallback_count,
            summary.primary_key_calls,
            summary.fallback_key_calls,
            summary.models_used,
        )
        self.last_summary = summary
        return catalog

    def run(
        self,
        store_catalogs: list[dict[str, Any]],
        out_dir: Path,
    ) -> UnifiedCatalog:
        """Combine store catalogs and enrich via SovereignEG Pipeline B."""
        combiner = CatalogCombiner()
        unified_catalog = combiner.combine_catalogs(store_catalogs)
        return self.enrich_unified_catalog(unified_catalog, out_dir=out_dir)


__all__ = [
    "DEFAULT_SOVEREIGN_CACHE_FILENAME",
    "SovereignRunSummary",
    "SovereignSmallBatchPipeline",
]
