"""Master Pipeline Orchestrator.

Wires all 7 layers together into a coherent, robust extraction pipeline:
1. Scraping using Scrapling base engine & raw archival.
2. Text sanitizer layer.
3. CPU Extraction using ground-truth CPU_SPECS.
4. Deterministic extractor layer (with Section-Level envelope capture).
5. Physical validation layer (Gate 1 - deterministic evaluation).
6. AI Fallback layer (via unified IAIFallbackExtractor contract).
7. Physical validation layer (Gate 2 - AI fallback evaluation).
"""

from __future__ import annotations

import logging
import copy
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.engine.scrapling_engine import ScraplingEngine
from pipeline.ai_fallback.base import IAIFallbackExtractor
from pipeline.cpu_anchor import CPUAnchorExtractor
from pipeline.deterministic import DeterministicExtractor
from pipeline.physical_validator import PhysicalValidator
from pipeline.provenance import ProvenanceTracker
from pipeline.raw_storage import RawScrapeStorage
from pipeline.sanitizer import TextSanitizer
from pipeline.schema import EnvelopeResult, ExtractionEnvelope, RawScrapedProduct

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """End-to-end extraction result with full auditability."""
    specs: Dict[str, Any]
    cpu_key: Optional[str]
    envelopes_generated: List[ExtractionEnvelope] = field(default_factory=list)
    ai_results: List[EnvelopeResult] = field(default_factory=list)
    validation_rejections: List[Dict[str, Any]] = field(default_factory=list)
    raw_product: Optional[RawScrapedProduct] = None
    provenance_record: Optional[Dict[str, Any]] = None


class LaptopExtractionPipeline:
    """Full 7-layer scraping and hardware extraction pipeline."""

    def __init__(
        self,
        ai_fallback: Optional[IAIFallbackExtractor] = None,
        scraper_engine: Optional[ScraplingEngine] = None,
        raw_storage: Optional[RawScrapeStorage] = None,
    ) -> None:
        self.ai_fallback = ai_fallback
        self.scraper_engine = scraper_engine or ScraplingEngine()
        self.raw_storage = raw_storage or RawScrapeStorage()
        self.sanitizer = TextSanitizer()
        self.cpu_anchor = CPUAnchorExtractor()
        self.deterministic = DeterministicExtractor()
        self.validator = PhysicalValidator()

    def process_raw_product(self, product: RawScrapedProduct) -> PipelineResult:
        """Run extraction layers 2 through 7 on a raw scraped product."""
        t0 = time.time()
        # --- Layer 2: Text Sanitizer ---
        sanitized_title = self.sanitizer.clean_text(product.title)
        sanitized_table = self.sanitizer.sanitize_table(product.raw_tables.get("specs", {}))
        sanitized_sections = self.sanitizer.sanitize_sections(product.raw_sections)

        # Flatten all tables into table dict if nested
        for tbl_name, tbl_rows in product.raw_tables.items():
            if tbl_name != "specs":
                cleaned_rows = self.sanitizer.sanitize_table(tbl_rows)
                for k, v in cleaned_rows.items():
                    if k not in sanitized_table:
                        sanitized_table[k] = v

        # --- Layer 3: CPU Anchor Extraction ---
        spec_text_snippets = list(sanitized_table.values()) + list(sanitized_sections.values())
        cpu_specs, cpu_context, cpu_key = self.cpu_anchor.extract(
            title=sanitized_title,
            spec_texts=spec_text_snippets,
        )

        # --- Layer 4: Deterministic Extractor ---
        specs, envelopes = self.deterministic.extract(
            title=sanitized_title,
            sanitized_table=sanitized_table,
            sanitized_sections=sanitized_sections,
            cpu_context=cpu_context,
        )

        # Merge CPU ground-truth specs (Option A: absolute ground truth)
        if cpu_specs:
            cpu_raw_spec = specs.get("cpu", {}).get("raw_spec")
            specs["cpu"] = cpu_specs
            if cpu_raw_spec:
                specs["cpu"]["raw_spec"] = cpu_raw_spec

        deterministic_specs = copy.deepcopy(specs)

        # --- Layer 5: Physical Validation Gate 1 (Deterministic specs) ---
        validation_rejections: List[Dict[str, Any]] = []
        for cat, cat_dict in list(specs.items()):
            if cat == "cpu":
                continue  # CPU is already verified ground truth
            for f_name, f_val in list(cat_dict.items()):
                field_path = f"{cat}.{f_name}"
                is_valid, cleaned_val, reason = self.validator.validate_field(
                    field_path=field_path,
                    value=f_val,
                    cpu_context=cpu_context,
                )
                if not is_valid:
                    validation_rejections.append({
                        "gate": 1,
                        "field_path": field_path,
                        "rejected_value": f_val,
                        "reason": reason,
                    })
                    # Clear invalid deterministic value
                    specs[cat][f_name] = None
                    # Package into envelope for AI resolution
                    if cat == "identity":
                        raw_context = self.deterministic.clean_laptop_name(sanitized_title)
                        allowed_vals = (
                            self.deterministic.CANONICAL_FAMILIES.get(specs.get("identity", {}).get("brand", ""), [])
                            if field_path == "identity.laptop_family"
                            else None
                        )
                    else:
                        raw_context = sanitized_sections.get(cat.capitalize(), "") or str(sanitized_table)
                        allowed_vals = None

                    envelopes.append(
                        ExtractionEnvelope(
                            field_path=field_path,
                            field_description=f"Hardware spec for {field_path}",
                            raw_context=raw_context,
                            failure_reason="validation_failed",
                            expected_type="str" if isinstance(f_val, str) else "float",
                            cpu_context=cpu_context,
                            allowed_values=allowed_vals,
                        )
                    )
                else:
                    specs[cat][f_name] = cleaned_val

        # --- Layer 6: AI Fallback Layer ---
        ai_results: List[EnvelopeResult] = []
        if envelopes and self.ai_fallback:
            try:
                ai_results = self.ai_fallback.batch_extract_envelopes(envelopes)
            except Exception as e:
                logger.error("AI Fallback execution error: %s", e)

        # --- Layer 7: Physical Validation Gate 2 (AI Candidate evaluation) ---
        for ai_res in ai_results:
            if ai_res.extracted_value is None:
                continue

            parts = ai_res.field_path.split(".", 1)
            if len(parts) != 2:
                continue
            cat, f_name = parts

            is_valid, cleaned_val, reason = self.validator.validate_field(
                field_path=ai_res.field_path,
                value=ai_res.extracted_value,
                cpu_context=cpu_context,
            )

            if is_valid and cleaned_val is not None:
                # Accept validated AI extraction
                specs[cat][f_name] = cleaned_val
            else:
                validation_rejections.append({
                    "gate": 2,
                    "field_path": ai_res.field_path,
                    "rejected_value": ai_res.extracted_value,
                    "model": ai_res.model_name,
                    "reason": reason or "invalid_candidate",
                })

        # Build complete provenance & lineage audit record
        elapsed = time.time() - t0
        provenance_record = ProvenanceTracker.build_trace(
            raw_product=product,
            sanitized_title=sanitized_title,
            sanitized_table=sanitized_table,
            sanitized_sections=sanitized_sections,
            cpu_key=cpu_key,
            cpu_specs=cpu_specs,
            cpu_context=cpu_context,
            deterministic_specs=deterministic_specs,
            envelopes=envelopes,
            gate1_rejections=[r for r in validation_rejections if r.get("gate") == 1],
            ai_results=ai_results,
            gate2_rejections=[r for r in validation_rejections if r.get("gate") == 2],
            final_specs=specs,
            elapsed_s=elapsed,
        )

        return PipelineResult(
            specs=specs,
            cpu_key=cpu_key,
            envelopes_generated=envelopes,
            ai_results=ai_results,
            validation_rejections=validation_rejections,
            raw_product=product,
            provenance_record=provenance_record,
        )

    def parse_html(
        self,
        html_text: str,
        url: str = "",
        store_name: str = "compumarts",
    ) -> RawScrapedProduct:
        """Parse raw HTML into a structured RawScrapedProduct using PatternEngine."""
        from bs4 import BeautifulSoup
        from app.core.patterns.engine import PatternEngine

        soup = BeautifulSoup(html_text, "html.parser")
        title_elem = soup.select_one(
            "h1.product-title, h1.product__title, .product-meta__title, h1, .product-details h1"
        )
        title = title_elem.get_text(strip=True) if title_elem else ""
        if not title:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

        spec_res = PatternEngine.extract_specs(
            soup=soup,
            title=title,
            store_key=store_name.lower(),
        )

        return RawScrapedProduct(
            url=url,
            store=store_name,
            title=title,
            raw_html=html_text,
            raw_tables={"specs": spec_res.specs},
            raw_sections={"Description": spec_res.raw_description or ""},
            price=spec_res.price_val,
        )

    def extract_from_url(
        self,
        url: str,
        store_name: str = "compumarts",
        stealth: bool = False,
    ) -> PipelineResult:
        """Fetch URL with ScraplingEngine, archive raw HTML, and run full extraction."""
        # 1. Scrape via Scrapling
        scraped_doc = self.scraper_engine.fetch(url, stealth=stealth)

        # 2. Package raw product using PatternEngine
        raw_product = self.parse_html(
            html_text=scraped_doc.html,
            url=url,
            store_name=store_name,
        )

        # 3. Archive raw HTML for audits
        self.raw_storage.save(raw_product)

        # 4. Run pipeline
        return self.process_raw_product(raw_product)

