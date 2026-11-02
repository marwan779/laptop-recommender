"""Icecat Catalog Enricher & Post-Combiner LLM Fallback Orchestrator.

Executes Stage 3 (Icecat Matching & OpenIcecat Live JSON Spec Enrichment)
and Stage 4 (Targeted LLM Fallback for VARIANT_MATCH and NOT_FOUND laptops)
across a UnifiedCatalog.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.common.logger import get_logger
from app.matching.models import CanonicalLaptop, UnifiedCatalog, utcnow_str
from app.pipeline.icecat.api_service import IcecatAPIService
from app.pipeline.icecat.search_service import IcecatSearchService
from app.pipeline.icecat.web_spec_service import WebSpecSearchService
from app.pipeline.llm_auditor import LLMAuditor

logger = get_logger("pipeline.icecat.enricher")

SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_CACHE_PATH = SERVICE_ROOT / "scraping results" / "icecat_specs_cache.json"
DEFAULT_MATCH_REPORT_PATH = SERVICE_ROOT / "scraping results" / "icecat_match_report.json"

# Categories overwritten 100% by Icecat on EXACT_MATCH
EXACT_MATCH_OVERWRITE_CATEGORIES = (
    "memory",
    "storage",
    "display",
    "power_battery",
    "physical",
    "connectivity",
    "audio_webcam",
    "build_security",
)

# Chassis-only categories overwritten by Icecat on VARIANT_MATCH
VARIANT_MATCH_CHASSIS_CATEGORIES = (
    "power_battery",
    "physical",
    "connectivity",
    "audio_webcam",
    "build_security",
)

# Variant-specific categories allowed to be refined by LLMAuditor on VARIANT_MATCH
VARIANT_LLM_ALLOWED_CATEGORIES = {
    "memory",
    "storage",
    "display",
    "operating_system",
    "identity",
}


class IcecatCatalogEnricher:
    """Enriches UnifiedCatalog laptops with Icecat specs and runs targeted LLM fallback."""

    def __init__(
        self,
        cache_path: Path | str = DEFAULT_CACHE_PATH,
        match_report_path: Path | str = DEFAULT_MATCH_REPORT_PATH,
        search_delay: float = 5.5,
        api_delay: float = 0.2,
        run_llm_fallback: bool = True,
        enable_web_search: bool = True,
        auditor: LLMAuditor | None = None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.match_report_path = Path(match_report_path)
        self.search_service = IcecatSearchService(base_delay=search_delay)
        self.api_service = IcecatAPIService(request_delay=api_delay)
        self.web_spec_service = WebSpecSearchService()
        self.run_llm_fallback = run_llm_fallback
        self.enable_web_search = enable_web_search
        self.auditor = auditor

        self.matches_cache: dict[str, dict[str, Any]] = {}
        self.specs_by_icecat_id: dict[str, dict[str, Any]] = {}
        self.llm_cache: dict[str, dict[str, Any]] = {}
        self.web_specs_cache: dict[str, str] = {}
        self._load_caches()

    def _load_caches(self) -> None:
        """Load persistent Icecat match & spec caches, seeding from icecat_match_report.json if present."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, encoding="utf-8") as f:
                    data = json.load(f)
                self.matches_cache = data.get("matches_by_canonical_id", {}) or {}
                self.specs_by_icecat_id = data.get("specs_by_icecat_id", {}) or {}
                self.llm_cache = data.get("llm_stage4_by_canonical_id", {}) or {}
                self.web_specs_cache = data.get("web_specs_by_canonical_id", {}) or {}
            except Exception as e:
                logger.warning("Failed to load Icecat cache (%s): %s", self.cache_path, e)

        # Seed matches_cache from existing icecat_match_report.json if not already cached
        if self.match_report_path.exists():
            try:
                with open(self.match_report_path, encoding="utf-8") as f:
                    report = json.load(f)
                seeded = 0
                for item in report.get("found_laptops", []) or []:
                    cid = item.get("canonical_id")
                    if cid and cid not in self.matches_cache:
                        self.matches_cache[cid] = {
                            "match_status": item.get("match_status", "EXACT_MATCH"),
                            "icecat_product_id": item.get("icecat_product_id"),
                            "icecat_title": item.get("icecat_title"),
                            "icecat_mpn": item.get("icecat_mpn"),
                            "icecat_url": item.get("icecat_url"),
                            "matched_query": item.get("matched_query"),
                        }
                        seeded += 1
                if seeded:
                    logger.info("Seeded %d Icecat matches from %s", seeded, self.match_report_path.name)
            except Exception as e:
                logger.warning("Failed to seed from match report (%s): %s", self.match_report_path, e)

    def _save_caches(self) -> None:
        """Persist Icecat matches and parsed API specs to disk."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": utcnow_str(),
                "matches_by_canonical_id": self.matches_cache,
                "specs_by_icecat_id": self.specs_by_icecat_id,
                "llm_stage4_by_canonical_id": self.llm_cache,
                "web_specs_by_canonical_id": self.web_specs_cache,
            }
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("Failed to save Icecat cache: %s", e)

    def get_or_fetch_web_specs(self, lap: CanonicalLaptop) -> str:
        """Retrieve Scrapling online reference specs from cache or fetch live from DuckDuckGo Lite."""
        if lap.canonical_id in self.web_specs_cache:
            return self.web_specs_cache[lap.canonical_id]
        if not self.enable_web_search:
            return ""
        online_text = self.web_spec_service.fetch_online_specs(lap)
        self.web_specs_cache[lap.canonical_id] = online_text
        return online_text

    @staticmethod
    def _has_complete_chassis_specs(specs: dict[str, Any]) -> bool:
        """Check whether key chassis specs (battery Wh, weight kg, ports, wifi) are all populated."""
        pb = specs.get("power_battery") or {}
        ph = specs.get("physical") or {}
        cn = specs.get("connectivity") or {}
        return bool(
            pb.get("battery_capacity_wh")
            and ph.get("weight_kg")
            and cn.get("ports")
            and cn.get("wifi")
        )

    def get_or_fetch_icecat_specs(self, icecat_id: int | str) -> dict[str, dict[str, Any]] | None:
        """Retrieve parsed Icecat specs from cache or fetch live from OpenIcecat API."""
        key = str(icecat_id)
        if key in self.specs_by_icecat_id:
            return self.specs_by_icecat_id[key]

        raw_data = self.api_service.fetch_product_data(icecat_id)
        if not raw_data:
            return None

        parsed = self.api_service.parse_product_json(raw_data)
        self.specs_by_icecat_id[key] = parsed
        return parsed

    @staticmethod
    def apply_icecat_specs_to_laptop(
        laptop: CanonicalLaptop,
        icecat_specs: dict[str, dict[str, Any]],
        match_status: str,
    ) -> None:
        """Merge Icecat specifications into CanonicalLaptop according to the Ownership Matrix.

        Rules:
        1. CPU & GPU Dictionaries: Keep 100% as-is from our local dictionaries.
           Exception: Inject `tdp_w` / `max_turbo_power_w` / `npu_tops` / `vram_type` if missing.
        2. Regional & Store Fields: Never overwrite `operating_system.name`, `mpn`, `price_egp`, `offers`.
           Only fill `identity.color` from Icecat if our store color is None.
        3. EXACT_MATCH: Overwrite all non-regional, non-dictionary hardware categories
           (`memory`, `storage`, `display`, `power_battery`, `physical`, `connectivity`,
            `audio_webcam`, `build_security`).
        4. VARIANT_MATCH: Overwrite chassis-level categories (`power_battery`, `physical`,
           `connectivity`, `audio_webcam`, `build_security`) and chassis slot/interface sub-fields,
           while preserving the Egyptian store's `memory.capacity_gb`, `storage.capacity_gb`, and `display`.
        """
        specs = laptop.specs

        # 1. Identity: Only fill color if missing on store
        ident = specs.setdefault("identity", {})
        if not ident.get("color") and icecat_specs.get("identity", {}).get("color"):
            ident["color"] = icecat_specs["identity"]["color"]

        # 2. CPU TDP / NPU injection (never overwrite existing CPU dictionary fields)
        cpu_dict = specs.setdefault("cpu", {})
        for cpu_supp_key in ("tdp_w", "max_turbo_power_w", "npu_tops"):
            val = icecat_specs.get("cpu", {}).get(cpu_supp_key)
            if val is not None and cpu_dict.get(cpu_supp_key) is None:
                cpu_dict[cpu_supp_key] = val

        # 3. GPU TDP / VRAM type injection (never overwrite existing GPU dictionary fields)
        gpu_dict = specs.setdefault("gpu", {})
        if not gpu_dict.get("integrated"):
            for gpu_supp_key in ("tdp_w", "vram_type"):
                val = icecat_specs.get("gpu", {}).get(gpu_supp_key)
                if val is not None and gpu_dict.get(gpu_supp_key) is None:
                    gpu_dict[gpu_supp_key] = val

        # 4. Category Overwrites based on EXACT_MATCH vs VARIANT_MATCH
        if match_status == "EXACT_MATCH":
            for cat in EXACT_MATCH_OVERWRITE_CATEGORIES:
                cat_target = specs.setdefault(cat, {})
                cat_source = icecat_specs.get(cat, {}) or {}
                for f_name, f_val in cat_source.items():
                    if f_val is not None:
                        cat_target[f_name] = f_val
        elif match_status == "VARIANT_MATCH":
            # Overwrite chassis-level categories
            for cat in VARIANT_MATCH_CHASSIS_CATEGORIES:
                cat_target = specs.setdefault(cat, {})
                cat_source = icecat_specs.get(cat, {}) or {}
                for f_name, f_val in cat_source.items():
                    if f_val is not None:
                        cat_target[f_name] = f_val

            # For memory & storage on VARIANT_MATCH, keep store capacity_gb, populate chassis slots/interface
            mem_target = specs.setdefault("memory", {})
            for f_name in ("memory_type", "speed", "slot_count", "max_supported_gb", "is_soldered"):
                f_val = (icecat_specs.get("memory") or {}).get(f_name)
                if f_val is not None and mem_target.get(f_name) is None:
                    mem_target[f_name] = f_val

            stor_target = specs.setdefault("storage", {})
            for f_name in ("storage_type", "interface", "form_factor", "slot_count"):
                f_val = (icecat_specs.get("storage") or {}).get(f_name)
                if f_val is not None and stor_target.get(f_name) is None:
                    stor_target[f_name] = f_val

    def enrich_catalog(
        self,
        catalog: UnifiedCatalog,
        allow_live_search: bool = True,
    ) -> UnifiedCatalog:
        """Run Stage 3 (Icecat Enrichment) and Stage 4 (Targeted LLM Fallback) on UnifiedCatalog."""
        total = len(catalog.laptops)
        logger.info("Starting Stage 3 Icecat Enrichment for %d unique laptops...", total)

        variant_laptops: list[CanonicalLaptop] = []
        not_found_laptops: list[CanonicalLaptop] = []

        for idx, laptop in enumerate(catalog.laptops, 1):
            cid = laptop.canonical_id
            match_info = self.matches_cache.get(cid)

            if not match_info and allow_live_search:
                logger.info("[%d/%d] Searching Icecat for %s...", idx, total, cid)
                match_info = self.search_service.match_laptop(laptop.model_dump())
                if match_info.get("match_status") in ("EXACT_MATCH", "VARIANT_MATCH"):
                    self.matches_cache[cid] = match_info

            status = (match_info or {}).get("match_status") or "NOT_FOUND"
            icecat_id = (match_info or {}).get("icecat_product_id")

            laptop.icecat_match_type = status
            laptop.icecat_product_id = icecat_id
            laptop.icecat_mpn = (match_info or {}).get("icecat_mpn")
            laptop.icecat_url = (match_info or {}).get("icecat_url")

            if status in ("EXACT_MATCH", "VARIANT_MATCH") and icecat_id:
                icecat_specs = self.get_or_fetch_icecat_specs(icecat_id)
                if icecat_specs:
                    self.apply_icecat_specs_to_laptop(laptop, icecat_specs, status)
                    if status == "EXACT_MATCH":
                        laptop.verification_status = "VERIFIED_ICECAT"
                    else:
                        variant_laptops.append(laptop)
                else:
                    not_found_laptops.append(laptop)
            else:
                laptop.icecat_match_type = "NOT_FOUND"
                not_found_laptops.append(laptop)

            if idx % 25 == 0:
                self._save_caches()

        self._save_caches()

        # --- Stage 4: Targeted Post-Combiner LLM Step (Only VARIANT_MATCH & NOT_FOUND) ---
        if self.run_llm_fallback and (variant_laptops or not_found_laptops):
            self._run_targeted_llm_stage(variant_laptops, not_found_laptops)
        else:
            # If LLM fallback is disabled, mark remaining without LLM verification as NOT_FOUND
            for lap in variant_laptops:
                if lap.verification_status != "VERIFIED_ICECAT_VARIANT":
                    lap.verification_status = "NOT_FOUND"
            for lap in not_found_laptops:
                if lap.verification_status != "LLM_EXTRACTED":
                    lap.verification_status = "NOT_FOUND"

        exact_cnt = sum(1 for l in catalog.laptops if l.verification_status == "VERIFIED_ICECAT")
        var_cnt = sum(1 for l in catalog.laptops if l.verification_status == "VERIFIED_ICECAT_VARIANT")
        llm_cnt = sum(1 for l in catalog.laptops if l.verification_status == "LLM_EXTRACTED")
        nf_cnt = sum(1 for l in catalog.laptops if l.verification_status == "NOT_FOUND")

        logger.info(
            "Stage 3 & 4 Complete: VERIFIED_ICECAT=%d | VERIFIED_ICECAT_VARIANT=%d | LLM_EXTRACTED=%d | NOT_FOUND=%d",
            exact_cnt,
            var_cnt,
            llm_cnt,
            nf_cnt,
        )
        return catalog

    def _run_targeted_llm_stage(
        self,
        variant_laptops: list[CanonicalLaptop],
        not_found_laptops: list[CanonicalLaptop],
    ) -> None:
        """Execute Stage 4 Cloud LLM verification/extraction strictly on VARIANT_MATCH and NOT_FOUND laptops."""
        if self.auditor is None:
            try:
                self.auditor = LLMAuditor()
            except Exception as e:
                logger.warning("Could not initialize LLMAuditor for Stage 4 (%s). Remaining items stay NOT_FOUND.", e)
                for lap in variant_laptops + not_found_laptops:
                    lap.verification_status = "NOT_FOUND"
                return

        total_llm = len(variant_laptops) + len(not_found_laptops)
        logger.info(
            "Starting Stage 4 Targeted LLM Fallback on %d VARIANT_MATCH and %d NOT_FOUND laptops (%d total)...",
            len(variant_laptops),
            len(not_found_laptops),
            total_llm,
        )

        idx = 0
        # 1. Process VARIANT_MATCH laptops (Scoped to variant-specific categories only)
        for lap in variant_laptops:
            idx += 1
            cached_llm = self.llm_cache.get(lap.canonical_id)
            if cached_llm and cached_llm.get("verification_status") == "VERIFIED_ICECAT_VARIANT":
                lap.specs = cached_llm["specs"]
                lap.verification_status = "VERIFIED_ICECAT_VARIANT"
                logger.info(
                    "[Stage 4 LLM %d/%d] Restored VARIANT_MATCH %s from cache",
                    idx,
                    total_llm,
                    lap.canonical_id,
                )
                continue

            if getattr(self.auditor, "is_circuit_broken", False):
                lap.verification_status = "NOT_FOUND"
                continue

            logger.info("[Stage 4 LLM %d/%d] Auditing VARIANT_MATCH %s...", idx, total_llm, lap.canonical_id)
            audit_input = self._build_auditor_record(lap, allowed_categories=VARIANT_LLM_ALLOWED_CATEGORIES)
            try:
                batch_res = self.auditor.audit_batch([audit_input], identifiers=[lap.canonical_id])
                p_res = batch_res.audited_laptops[0] if batch_res.audited_laptops else None
                if p_res and p_res.is_audited:
                    applied_cnt = 0
                    if p_res.corrections:
                        applied = self.auditor.apply_corrections(
                            audit_input,
                            p_res.corrections,
                            allowed_categories=VARIANT_LLM_ALLOWED_CATEGORIES,
                        )
                        applied_cnt = len(applied)
                        lap.specs = audit_input["specs"]
                    lap.verification_status = "VERIFIED_ICECAT_VARIANT"
                    self.llm_cache[lap.canonical_id] = {
                        "verification_status": "VERIFIED_ICECAT_VARIANT",
                        "specs": lap.specs,
                    }
                    logger.info(
                        "[Stage 4 LLM %d/%d] Verified VARIANT_MATCH %s via %s (%d corrections applied)",
                        idx,
                        total_llm,
                        lap.canonical_id,
                        batch_res.provider,
                        applied_cnt,
                    )
                else:
                    lap.verification_status = "NOT_FOUND"
                    logger.warning(
                        "[Stage 4 LLM %d/%d] Could not verify VARIANT_MATCH %s; keeping NOT_FOUND",
                        idx,
                        total_llm,
                        lap.canonical_id,
                    )
            except Exception as e:
                logger.warning("Stage 4 LLM failed for VARIANT_MATCH %s: %s", lap.canonical_id, e)
                lap.verification_status = "NOT_FOUND"

            if idx % 5 == 0:
                self._save_caches()

        # 2. Process NOT_FOUND laptops (Full non-silicon spec extraction/repair + Scrapling Web Search for missing chassis fields)
        for lap in not_found_laptops:
            idx += 1
            cached_llm = self.llm_cache.get(lap.canonical_id)
            if cached_llm and cached_llm.get("verification_status") == "LLM_EXTRACTED":
                cached_specs = cached_llm["specs"]
                if (
                    cached_llm.get("web_enriched")
                    or not self.enable_web_search
                    or self._has_complete_chassis_specs(cached_specs)
                ):
                    lap.specs = cached_specs
                    lap.verification_status = "LLM_EXTRACTED"
                    logger.info(
                        "[Stage 4 LLM %d/%d] Restored NOT_FOUND %s from cache (LLM_EXTRACTED)",
                        idx,
                        total_llm,
                        lap.canonical_id,
                    )
                    continue
                # Preserve store-extracted specs from prior run and enrich missing nulls with Scrapling web search
                lap.specs = cached_specs

            if getattr(self.auditor, "is_circuit_broken", False):
                lap.verification_status = "NOT_FOUND"
                continue

            online_specs = ""
            if self.enable_web_search and not self._has_complete_chassis_specs(lap.specs):
                logger.info(
                    "[Stage 4 LLM %d/%d] Searching online specs via Scrapling for NOT_FOUND %s...",
                    idx,
                    total_llm,
                    lap.canonical_id,
                )
                online_specs = self.get_or_fetch_web_specs(lap)

            logger.info("[Stage 4 LLM %d/%d] Extracting NOT_FOUND %s...", idx, total_llm, lap.canonical_id)
            audit_input = self._build_auditor_record(lap, online_specs=online_specs)
            try:
                batch_res = self.auditor.audit_batch([audit_input], identifiers=[lap.canonical_id])
                p_res = batch_res.audited_laptops[0] if batch_res.audited_laptops else None
                if p_res and p_res.is_audited:
                    applied_cnt = 0
                    if p_res.corrections:
                        applied = self.auditor.apply_corrections(audit_input, p_res.corrections)
                        applied_cnt = len(applied)
                        lap.specs = audit_input["specs"]
                    lap.verification_status = "LLM_EXTRACTED"
                    self.llm_cache[lap.canonical_id] = {
                        "verification_status": "LLM_EXTRACTED",
                        "web_enriched": True,
                        "specs": lap.specs,
                    }
                    logger.info(
                        "[Stage 4 LLM %d/%d] Extracted NOT_FOUND %s -> LLM_EXTRACTED via %s (%d fields filled/corrected)",
                        idx,
                        total_llm,
                        lap.canonical_id,
                        batch_res.provider,
                        applied_cnt,
                    )
                else:
                    lap.verification_status = "NOT_FOUND"
                    logger.warning(
                        "[Stage 4 LLM %d/%d] Could not extract NOT_FOUND %s; keeping NOT_FOUND",
                        idx,
                        total_llm,
                        lap.canonical_id,
                    )
            except Exception as e:
                logger.warning("Stage 4 LLM failed for NOT_FOUND %s: %s", lap.canonical_id, e)
                lap.verification_status = "NOT_FOUND"

            if idx % 5 == 0:
                self._save_caches()

        self._save_caches()

    @staticmethod
    def _build_auditor_record(
        lap: CanonicalLaptop,
        allowed_categories: set[str] | None = None,
        online_specs: str = "",
    ) -> dict[str, Any]:
        """Construct the dictionary format expected by LLMAuditor.audit_batch()."""
        ctx = lap.raw_store_context or {}
        source_table = dict(ctx.get("source_table") or {})
        raw_desc = ctx.get("raw_description") or ""
        if raw_desc and "Description" not in source_table:
            source_table["Description"] = raw_desc
        if online_specs:
            source_table["Online_Reference_Specs"] = online_specs
        record: dict[str, Any] = {
            "url": ctx.get("primary_url") or (lap.offers[0].product_url if lap.offers else lap.canonical_id),
            "title": lap.title,
            "specs": lap.specs,
            "source_table": source_table,
        }
        if allowed_categories is not None:
            record["allowed_categories"] = allowed_categories
        return record
