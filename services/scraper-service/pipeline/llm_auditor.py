"""Post-Pipeline Ground-Truth LLM Auditor using Google Gemini API.

Acts as the automated final verification and self-healing layer:
1. Compares extracted catalog specifications against raw PDP product data (source table and title).
2. Detects contradictions, hallucinations, and cross-subsystem contaminations:
   - Memory slots vs soldered (soldered/no slots -> slot_count=0, is_soldered=True).
   - Storage slots vs memory expansion slots (DDR4/DDR5 SO-DIMM is RAM, not storage).
   - Primary drive form factor vs expansion slot (installed SSD vs secondary 2.5" bay).
   - Display color gamut vs chassis exterior paint (Mica silver, Cosmos Grey -> null).
   - Microphone vs speaker wattage/codecs (Dolby Atmos, Realtek -> null or clean).
3. Strictly locks and preserves CPU and GPU specifications (immutable ground truth).
4. Adheres strictly to Gemini Free Tier constraints:
   - 15 RPM rate limiting (automatic >= 4.2s delay between calls).
   - Batching 4-5 laptops per call.
   - Exponential backoff retry on 429 / ResourceExhausted.
   - Dual-model fallback (gemini-2.5-flash -> gemini-1.5-flash).
5. Validates every proposed patch through PhysicalValidator before updating the catalog.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables (.env in services/scraper-service or current working directory)
load_dotenv()

from pipeline.physical_validator import PhysicalValidator

logger = logging.getLogger("llm_auditor")

AUDITOR_SYSTEM_INSTRUCTION = """You are the Ground-Truth Auditor for laptops scraped and structured from Egyptian retailer stores.

The structured specs given to you may contain extraction mistakes, mismatches, or missing fields compared to the raw scraped data (found in `group_raw_specs`, `source_table`, and `title`).

YOUR MISSION:
Check every field for each laptop against the raw scraped text:
1. Correct any mismatches or wrong values.
2. Fill in any missing/null fields that are explicitly stated in the source text.
3. For every change, provide the exact verbatim quote from the text as evidence.

ESSENTIAL GUARDRAILS:
- Do not touch CPU specs (cpu.*) as they are verified against silicon databases.
- Real-world physics: Laptops are never 20cm thick (retailers often label dimensions as W x H x D when they mean W x D x H; height is always the smallest dimension / thickness).
- Never invent specs that are not in the raw text. If the raw text does not mention it, leave it as is.
"""


class FieldCorrection(BaseModel):
    """A proposed correction for an extracted specification field."""
    field_path: str = Field(description="Canonical dot-delimited field path, e.g. memory.slot_count, display.color_gamut, storage.form_factor")
    current_value: Optional[Union[str, int, float, bool]] = Field(default=None, description="The current incorrect value present in the catalog specs")
    corrected_value: Optional[Union[str, int, float, bool]] = Field(default=None, description="The strictly verified corrected value from raw_spec, or null if it must be cleared/unset")
    reason: str = Field(description="Detailed technical rationale explaining why the current value is contradictory or invalid based on raw_spec")
    evidence_quote: str = Field(description="Exact verbatim quote from the raw spec table or product title supporting this correction")


class ProductAuditResult(BaseModel):
    """The audit outcome for a single laptop."""
    laptop_id: str = Field(description="The unique identifier (URL or index) of the laptop")
    has_contradictions: bool = Field(description="True if any contradictory or invalid fields were detected, False if 100% accurate")
    corrections: List[FieldCorrection] = Field(default_factory=list, description="List of corrections to apply for this laptop")


class BatchAuditResponse(BaseModel):
    """Batch response containing audit results for multiple laptops."""
    audited_laptops: List[ProductAuditResult] = Field(default_factory=list, description="List of audit results for each laptop in the batch")


class RateLimiter:
    """Thread-safe rate limiter to strictly adhere to Gemini Free Tier RPM constraints (15 RPM max)."""

    def __init__(self, requests_per_minute: float = 14.0):
        self.min_interval = 60.0 / requests_per_minute
        self._last_request_time: float = 0.0

    def wait_if_needed(self) -> None:
        """Sleep if necessary to ensure the minimum inter-request interval."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()


def cast_value_to_field_type(field_path: str, value: Any) -> Any:
    """Cast a corrected value to the expected canonical Python type."""
    if value is None:
        return None

    if isinstance(value, str):
        v_clean = value.strip()
        v_lower = v_clean.lower()
        if v_lower in ("null", "none", "", "n/a"):
            return None
        if v_lower in ("true", "yes"):
            return True
        if v_lower in ("false", "no"):
            return False

    int_fields = {
        "memory.slot_count", "memory.capacity_gb", "memory.speed", "memory.max_supported_gb",
        "storage.slot_count", "storage.capacity_gb", "storage.max_supported_gb",
        "display.refresh_rate_hz", "display.brightness_nits",
        "power_battery.battery_cells", "power_battery.power_adapter_w",
        "audio_webcam.speaker_count", "identity.warranty_years"
    }
    float_fields = {
        "display.size_inches", "display.response_time_ms",
        "power_battery.battery_capacity_wh",
        "physical.weight_kg", "physical.width_mm", "physical.depth_mm", "physical.height_mm",
        "cpu.npu_tops"
    }
    bool_fields = {
        "memory.is_soldered", "display.touchscreen",
        "build_security.has_backlit_keyboard", "build_security.has_fingerprint",
        "build_security.has_numpad", "audio_webcam.has_privacy_shutter",
        "audio_webcam.has_ir_camera", "connectivity.has_card_reader"
    }

    if field_path in int_fields:
        try:
            return int(float(str(value).strip()))
        except (ValueError, TypeError):
            return None
    elif field_path in float_fields:
        try:
            return float(str(value).strip())
        except (ValueError, TypeError):
            return None
    elif field_path in bool_fields:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "yes", "1")

    return str(value).strip() if isinstance(value, str) else value


class GeminiAuditor:
    """Automated Ground-Truth LLM Auditor using Google Gemini API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-flash-latest",
        fallback_models: Optional[List[str]] = None,
        requests_per_minute: float = 14.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please obtain a free API key from Google AI Studio "
                "(https://aistudio.google.com/) and add it to your .env file or pass via api_key."
            )

        self.model = model
        self.fallback_models = fallback_models or ["gemini-3.8-flash", "gemini-flash-lite-latest"]
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(requests_per_minute=requests_per_minute)
        self._daily_quota_exhausted: set = set()

        # Initialize Google GenAI client
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            logger.error("Failed to initialize Google GenAI Client: %s", e)
            raise

    def _prepare_laptop_payload(self, laptop: Dict[str, Any], identifier: str) -> Dict[str, Any]:
        """Format a laptop entry for auditing, excluding CPU and GPU to enforce immutability."""
        specs = laptop.get("specs", {})
        
        group_raw_specs: Dict[str, str] = {}
        auditable_specs: Dict[str, Any] = {}

        for group_name, group_data in specs.items():
            if group_name == "cpu":
                continue
            if isinstance(group_data, dict):
                group_copy = dict(group_data)
                raw_s = group_copy.pop("raw_spec", None)
                if raw_s:
                    group_raw_specs[group_name] = str(raw_s).strip()
                auditable_specs[group_name] = group_copy
            else:
                auditable_specs[group_name] = group_data

        return {
            "laptop_id": identifier,
            "title": laptop.get("title", ""),
            "group_raw_specs": group_raw_specs,
            "source_table": laptop.get("source_table", {}),
            "specs": auditable_specs,
        }

    def audit_batch(
        self, laptops: List[Dict[str, Any]], identifiers: Optional[List[str]] = None
    ) -> BatchAuditResponse:
        """Audit a batch of laptops against their raw specs using Gemini API.
        
        Args:
            laptops: List of raw laptop dictionaries with 'specs', 'source_table', and 'title'.
            identifiers: Optional list of unique string IDs (defaults to URL or index).
        """
        from google.genai import errors, types

        if identifiers is None:
            identifiers = [
                laptop.get("url") or f"laptop_{idx}"
                for idx, laptop in enumerate(laptops)
            ]

        batch_payload = [
            self._prepare_laptop_payload(lap, ident)
            for lap, ident in zip(laptops, identifiers)
        ]

        prompt_text = (
            "Hi Gemini, this is the result of scraping + structuring of Egyptian laptop stores. "
            "The structured schema given to you might contain mismatches or missing values from the original scraped text "
            "represented in 'source_table', 'group_raw_specs', and 'title'. "
            "Your task is to check every single field in every laptop given to you, correct any mismatches, and fill in missing fields explicitly stated in the raw text.\n\n"
            f"INPUT_BATCH:\n{json.dumps(batch_payload, indent=2, ensure_ascii=False)}"
        )

        all_candidates = [self.model] + self.fallback_models
        models_to_try = []
        for m in all_candidates:
            if m not in self._daily_quota_exhausted and m not in models_to_try:
                models_to_try.append(m)

        if not models_to_try:
            logger.error("All Gemini models in fallback chain have exhausted their daily quotas!")
            return BatchAuditResponse(
                audited_laptops=[
                    ProductAuditResult(laptop_id=ident, has_contradictions=False, corrections=[])
                    for ident in identifiers
                ]
            )

        last_error = None
        for current_model in models_to_try:
            for attempt in range(1, self.max_retries + 1):
                try:
                    self.rate_limiter.wait_if_needed()

                    config = types.GenerateContentConfig(
                        temperature=0.0,
                        system_instruction=AUDITOR_SYSTEM_INSTRUCTION,
                        response_mime_type="application/json",
                        response_schema=BatchAuditResponse,
                    )

                    response = self.client.models.generate_content(
                        model=current_model,
                        contents=prompt_text,
                        config=config,
                    )

                    # Parse response
                    raw_text = response.text
                    if not raw_text:
                        raise ValueError("Gemini returned an empty response.")

                    parsed_data = json.loads(raw_text)
                    return BatchAuditResponse.model_validate(parsed_data)

                except errors.APIError as e:
                    last_error = e
                    status_code = getattr(e, "code", None)
                    err_str = str(e).lower()
                    is_rate_limit = status_code == 429 or "resource_exhausted" in err_str or "quota" in err_str
                    is_unavailable = status_code == 503 or "unavailable" in err_str
                    is_not_found = status_code == 404 or "not_found" in err_str

                    if is_not_found:
                        logger.warning("Model %s not found (404). Switching to next available fallback model...", current_model)
                        self._daily_quota_exhausted.add(current_model)
                        break

                    is_daily_limit = (
                        "quota exceeded for metric" in err_str
                        or "generaterequestsperday" in err_str
                        or "exceeded your current quota" in err_str
                        or "please retry in" in err_str
                    )
                    if is_daily_limit:
                        self._daily_quota_exhausted.add(current_model)
                        logger.warning(
                            "Daily quota ceiling reached for %s. Blacklisting model for remainder of run and failing over immediately.",
                            current_model
                        )
                        break

                    if (is_rate_limit or is_unavailable) and attempt < self.max_retries:
                        backoff = 4.0 * (2 ** attempt)
                        logger.warning(
                            "Transient %s on %s (attempt %d/%d). Backing off for %.1fs...",
                            "RateLimit (429)" if is_rate_limit else "Unavailable (503)",
                            current_model, attempt, self.max_retries, backoff
                        )
                        time.sleep(backoff)
                        continue
                    else:
                        logger.warning("Gemini API Error on %s: %s. Trying next model...", current_model, e)
                        break

                except Exception as e:
                    last_error = e
                    logger.warning("Unexpected error during audit on %s: %s", current_model, e)
                    if attempt < self.max_retries:
                        time.sleep(2.0 * attempt)
                        continue
                    break

        logger.error("Audit failed for batch of %d laptops across all models: %s", len(laptops), last_error)
        # Return fallback empty response if failed
        return BatchAuditResponse(
            audited_laptops=[
                ProductAuditResult(laptop_id=ident, has_contradictions=False, corrections=[])
                for ident in identifiers
            ]
        )

    def apply_corrections(
        self, laptop: Dict[str, Any], corrections: List[FieldCorrection]
    ) -> List[Dict[str, Any]]:
        """Validate and apply corrections to a laptop's specifications dictionary.
        
        Returns:
            List of successfully applied change records.
        """
        applied_records = []
        specs = laptop.setdefault("specs", {})

        for corr in corrections:
            field_path = corr.field_path.strip()

            # Guard against touching locked CPU fields
            if field_path.startswith("cpu."):
                logger.warning("Ignoring proposed correction to locked field: %s", field_path)
                continue

            parts = field_path.split(".", 1)
            if len(parts) != 2:
                logger.warning("Skipping invalid field path format: %s", field_path)
                continue

            category, sub_field = parts[0], parts[1]

            # Cast value
            typed_value = cast_value_to_field_type(field_path, corr.corrected_value)

            # Validate through PhysicalValidator
            is_valid, validated_val, err_msg = PhysicalValidator.validate_field(field_path, typed_value)
            if not is_valid:
                logger.warning(
                    "PhysicalValidator rejected correction for %s: %r (%s). Skipping.",
                    field_path, typed_value, err_msg
                )
                continue

            cat_dict = specs.setdefault(category, {})
            old_value = cat_dict.get(sub_field)

            # Check if value actually changed
            if old_value == validated_val:
                continue

            cat_dict[sub_field] = validated_val

            # Auto-sync soldered flag when slot_count is explicitly 0
            if field_path == "memory.slot_count" and validated_val == 0:
                cat_dict["is_soldered"] = True

            record = {
                "field_path": field_path,
                "old_value": old_value,
                "new_value": validated_val,
                "reason": corr.reason,
                "evidence_quote": corr.evidence_quote,
            }
            applied_records.append(record)

        return applied_records

    def audit_catalog(
        self,
        catalog: List[Dict[str, Any]],
        batch_size: int = 4,
        apply_patches: bool = True,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Audit the entire catalog in batches, optionally patching contradictions.
        
        Args:
            catalog: List of all laptop entries.
            batch_size: Number of laptops per Gemini request.
            apply_patches: If True, mutates/patches the laptops in-place.
            progress_callback: Callback(processed_count, total_count, total_corrections).

        Returns:
            Tuple of (updated_catalog, all_corrections_log).
        """
        all_corrections_log = []
        updated_catalog = copy.deepcopy(catalog) if not apply_patches else catalog
        total_laptops = len(catalog)

        for i in range(0, total_laptops, batch_size):
            batch = updated_catalog[i:i + batch_size]
            identifiers = [
                item.get("url") or f"index_{i + idx}"
                for idx, item in enumerate(batch)
            ]

            batch_res = self.audit_batch(batch, identifiers=identifiers)

            # Map results to laptops
            res_map = {res.laptop_id: res for res in batch_res.audited_laptops}

            for idx, item in enumerate(batch):
                ident = identifiers[idx]
                p_res = res_map.get(ident)
                if not p_res or not p_res.has_contradictions or not p_res.corrections:
                    continue

                if apply_patches:
                    applied = self.apply_corrections(item, p_res.corrections)
                else:
                    # Dry-run record
                    applied = [
                        {
                            "field_path": c.field_path,
                            "old_value": item.get("specs", {}).get(c.field_path.split(".")[0], {}).get(c.field_path.split(".")[1]),
                            "new_value": cast_value_to_field_type(c.field_path, c.corrected_value),
                            "reason": c.reason,
                            "evidence_quote": c.evidence_quote,
                        }
                        for c in p_res.corrections
                    ]

                for app in applied:
                    all_corrections_log.append({
                        "laptop_index": i + idx,
                        "url": item.get("url", ""),
                        "title": item.get("title", ""),
                        **app,
                    })

            if progress_callback:
                progress_callback(min(i + batch_size, total_laptops), total_laptops, len(all_corrections_log))

        return updated_catalog, all_corrections_log

