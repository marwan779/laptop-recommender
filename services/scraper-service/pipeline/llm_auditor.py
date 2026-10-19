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
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables (.env in services/scraper-service or current working directory)
load_dotenv()

from pipeline.physical_validator import PhysicalValidator

logger = logging.getLogger("llm_auditor")

AUDITOR_SYSTEM_INSTRUCTION = """
You are a Semantic Ground-Truth Auditor for laptop specifications scraped from Egyptian retailer stores.

YOUR ROLE:
Audit the logical correctness and semantic consistency of already-structured laptop specifications against the available raw evidence:
- group_raw_specs
- source_table
- title

You are an auditor, NOT a re-extractor or a strict text-to-field matching engine.

Your job is to identify genuine data-quality problems by understanding what the source statements mean, how they relate to each other, and what each structured field represents according to the schema.

CORE AUDITING PRINCIPLE:
A difference in wording, representation, specificity, or value format is NOT automatically an error. Flag a field only when there is a meaningful reason to believe the structured data is incorrect, misleading, internally inconsistent, or unsupported by the available evidence.

AUDIT OBJECTIVES:

1. Detect genuine contradictions.
   Identify structured values that conflict with explicit source evidence, considering the meaning and context of both.
   Example: structured display resolution is 2560x1440, while the source explicitly specifies 2560x1600.

2. Detect incorrect semantic mappings.
   Determine whether the extracted value belongs to the field in which it was stored.
   Example: storing "No" in a general security_features field because the source says "Fingerprint Reader: No" incorrectly generalizes a statement about one feature to all security features.

3. Detect malformed or lossy representations.
   Identify values that discard important meaning or cannot be interpreted correctly under the schema.
   Example: a ports array containing ["Yes", "1", "1", "2", "5", "2"] without labels may lose the relationship between individual port types and their counts. Flag this only if the schema expects the array to represent port information and the representation genuinely prevents correct interpretation. Do not assume the representation is wrong without considering the schema.

4. Detect unsupported claims.
   Identify structured values that assert facts not supported by the available evidence when those values cannot reasonably be derived through valid normalization or established logical relationships.
   Distinguish between "not explicitly stated" and "contradicted by the source." Lack of evidence alone does not prove a value is false.

5. Detect meaningful omissions.
   Identify missing or null values only when the source provides sufficiently clear evidence to populate the field and doing so is consistent with the schema.
   Do not fill fields merely because a related fact appears in the source.

6. Resolve duplicate or conflicting source statements intelligently.
   The raw data may combine specification tables, product titles, descriptions, marketing text, repeated specifications, and retailer metadata.
   Consider the origin, specificity, context, and consistency of each statement.
   Explicit technical specifications generally carry more weight than vague promotional wording, but do not assume that every table entry is correct or every marketing statement is irrelevant.
   When credible sources disagree and the conflict cannot be resolved confidently, report ambiguity rather than declaring one value definitively wrong.

SEMANTIC NORMALIZATION:

Understand equivalent expressions and standard technical terminology.
Examples:
- "IEEE 802.11be" and "Wi-Fi 7" are equivalent descriptions of the wireless standard.
- "Bluetooth 5.4 or above" is compatible with a structured value of "Bluetooth 5.4"; the source does not establish a contradiction.
- "No OS" may correctly map to null when the schema uses null to represent no installed operating system.
- "Fingerprint Reader: No" supports has_fingerprint = false, but does not mean that all security features are absent.
- Units and equivalent representations may differ without indicating an error.
- A model name, part number, retailer SKU, and product family are distinct concepts even when their strings overlap.

Treat null, false, zero, empty arrays, and empty strings according to their meanings. They are not interchangeable:
- null can mean unknown, unspecified, unavailable, or not applicable, depending on the schema.
- false means a feature is explicitly absent or disabled.
- zero is a numeric value, not a synonym for unknown.
- an empty array means no items are represented; whether this implies absence depends on the schema and evidence.

Do not impose your own interpretation of a field when its schema semantics are unclear. Report a potential schema-dependent issue only when it is materially important.

CONFLICT ANALYSIS:

When the source contains apparently conflicting statements:
- Identify the exact statements and the fields they concern.
- Determine whether they refer to the same product configuration, component, quantity, or context.
- Distinguish explicit technical specifications from generic marketing text, bundled configurations, alternative configurations, and unrelated mentions.
- Do not automatically treat every mention of a different number as a contradiction.
- Do not automatically dismiss a statement merely because it appears in promotional text.
- If the evidence does not establish which value is correct, report an unresolved conflict with an appropriate confidence level instead of guessing.

For example, if a memory raw-spec field contains both "16GB DDR5 6400MT/s" and "32GB DDR5 + 1TB SSD," investigate whether these refer to the same configuration or whether one is generic promotional content. Do not automatically conclude that either value is correct or incorrect without sufficient contextual evidence.

SCOPE AND PROTECTION:

- Do not audit, modify, or report any CPU fields (cpu.*). These are verified against silicon databases.
- Do not audit, modify, or report any GPU fields (gpu.*).
- Audit all other fields and their relationships using the supplied evidence.
- Do not invent specifications, rely on assumed configurations of similar models, or silently introduce external facts.
- Do not use external knowledge to override the supplied source. General technical knowledge may help interpret terminology and logical relationships, but conclusions about the specific laptop must be evidence-based.
- Preserve correct structured values, even when their wording differs from the source.
- Do not make changes simply to improve formatting, naming style, or personal preference unless the representation causes a meaningful data-quality problem.
- Do not modify a correct field just because another representation is possible.

PHYSICAL PLAUSIBILITY:

Use physical constraints as a sanity check, not as an excuse to guess missing values.
Laptop thickness is normally much smaller than its width and depth. Retailer dimension labels may use different axis orders, so interpret the dimensions and units before judging them.
If dimensions appear implausible, flag the issue only when the evidence supports a genuine error or a likely axis-order mix-up. Do not silently reorder dimensions or invent corrected measurements without sufficient evidence.

EVIDENCE REQUIREMENTS:

Every reported finding must include:
- The exact field path.
- The current structured value.
- The relevant verbatim source quote(s), copied exactly from the supplied evidence.
- A concise explanation of the semantic problem.
- A classification: contradiction, incorrect mapping, malformed/lossy representation, unsupported claim, meaningful omission, or unresolved ambiguity.
- A confidence level: high, medium, or low.
- A recommended correction only when the evidence justifies one.

Evidence must genuinely support the finding. Do not quote unrelated text or treat a merely similar phrase as proof of a contradiction.
If a field is correct, do not report it.
If a potential issue depends on undocumented schema behavior, state that limitation rather than presenting it as a confirmed error.

AUDIT DECISION STANDARD:

Before reporting a finding, ask:
1. What does the structured field actually mean?
2. What does the source statement actually mean in context?
3. Do they genuinely conflict, or are they semantically compatible?
4. Could normalization, null semantics, alternative configurations, or marketing context explain the apparent difference?
5. Is there enough evidence to establish an actual error?
6. Would correcting the field improve factual correctness or preserve important meaning?

Report only findings that survive this reasoning process.
Prefer a small number of well-supported, actionable findings over a long list of superficial mismatches.
Do not invent problems to make the audit appear thorough.

The goal is trustworthy structured data, not perfect literal agreement between strings.
"""


class FieldCorrection(BaseModel):
    """A proposed correction for an extracted specification field."""
    field_path: str = Field(description="Canonical dot-delimited field path, e.g. memory.slot_count, display.color_gamut, storage.form_factor")
    current_value: Optional[Any] = Field(default=None, description="The current incorrect value present in the catalog specs")
    corrected_value: Optional[Any] = Field(default=None, description="The strictly verified corrected value from raw_spec, or null if it must be cleared/unset")
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


@dataclass
class LLMProviderEndpoint:
    """Configuration for an OpenAI-compatible LLM provider endpoint."""
    name: str
    base_url: str
    api_key_env: str
    model: str
    timeout_seconds: float = 45.0
    requests_per_minute: float = 30.0
    is_reasoning: bool = False


DEFAULT_ENDPOINTS: List[LLMProviderEndpoint] = [
    # 1. Primary: Groq Qwen 3.8 27B (Top-tier tabular / arithmetic / JSON reasoning at 500+ tok/s)
    LLMProviderEndpoint(
        name="groq-qwen-27b",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        model="qwen/qwen3.8-27b",
        is_reasoning=True,
        requests_per_minute=30.0,
    ),
    # 2. Fallback 1: Groq GPT-OSS 120B (Massive 120B open weights on Groq LPUs)
    LLMProviderEndpoint(
        name="groq-gpt-120b",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        model="openai/gpt-oss-120b",
        is_reasoning=False,
        requests_per_minute=30.0,
    ),
    # 3. Fallback 2: Groq GPT-OSS 20B (High speed, lower latency safety net)
    LLMProviderEndpoint(
        name="groq-gpt-20b",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        model="openai/gpt-oss-20b",
        is_reasoning=False,
        requests_per_minute=30.0,
    ),
    # 4. Fallback 3: Cerebras Llama 3.3 70B (Wafer-scale speed at 1,000+ tok/s)
    LLMProviderEndpoint(
        name="cerebras-llama-70b",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        model="llama-3.3-70b",
        is_reasoning=False,
        requests_per_minute=30.0,
    ),
    # 5. Fallback 4: SambaNova Llama 3.3 70B (Generous free-tier RDU cluster)
    LLMProviderEndpoint(
        name="sambanova-llama-70b",
        base_url="https://api.sambanova.ai/v1",
        api_key_env="SAMBANOVA_API_KEY",
        model="Meta-Llama-3.3-70B-Instruct",
        is_reasoning=False,
        requests_per_minute=30.0,
    ),
]


def _clean_json_text(text: str) -> str:
    """Strip markdown code fences and whitespace from a JSON string."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class LLMAuditor:
    """Universal High-Speed Ground-Truth LLM Auditor.
    
    Supports seamless multi-provider failover across OpenAI-compatible inference engines:
    Groq (Qwen 32B / Llama 70B) -> OpenRouter (Qwen 72B) -> Cerebras (Llama 70B) -> SambaNova.
    """

    def __init__(
        self,
        endpoints: Optional[List[LLMProviderEndpoint]] = None,
        max_retries: int = 2,
    ):
        self.max_retries = max_retries
        self._exhausted_endpoints: set = set()
        self._rate_limiters: Dict[str, RateLimiter] = {}
        self._clients: Dict[str, Any] = {}

        candidate_endpoints = list(endpoints or DEFAULT_ENDPOINTS)

        # Optional: Support local LLM (Ollama / vLLM / llama.cpp) if configured in .env
        local_base = os.getenv("LOCAL_LLM_BASE_URL") or os.getenv("OLLAMA_BASE_URL")
        if local_base:
            candidate_endpoints.insert(
                0,
                LLMProviderEndpoint(
                    name="local-llm",
                    base_url=local_base,
                    api_key_env="",
                    model=os.getenv("LOCAL_LLM_MODEL", "qwen2.5:32b"),
                    requests_per_minute=120.0,
                ),
            )

        # Optional: OpenAI-compatible Gemini endpoint if GEMINI_API_KEY is present
        # but none of the other primary keys are set
        has_primary_keys = any(os.getenv(ep.api_key_env, "") for ep in candidate_endpoints if ep.api_key_env)
        if not has_primary_keys and os.getenv("GEMINI_API_KEY"):
            candidate_endpoints.append(
                LLMProviderEndpoint(
                    name="gemini-openai-fallback",
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    api_key_env="GEMINI_API_KEY",
                    model="gemini-2.5-flash",
                    requests_per_minute=14.0,
                )
            )

        # Discover active endpoints with valid keys
        self.active_endpoints: List[LLMProviderEndpoint] = []
        for ep in candidate_endpoints:
            key = os.getenv(ep.api_key_env, "") if ep.api_key_env else "none"
            if key or not ep.api_key_env:
                self.active_endpoints.append(ep)
                self._rate_limiters[ep.name] = RateLimiter(requests_per_minute=ep.requests_per_minute)
                import openai
                self._clients[ep.name] = openai.OpenAI(
                    base_url=ep.base_url,
                    api_key=key or "none",
                    timeout=ep.timeout_seconds,
                )

        if not self.active_endpoints:
            logger.warning(
                "No active LLM provider API keys found in environment. "
                "Please configure at least one of GROQ_API_KEY, OPENROUTER_API_KEY, "
                "CEREBRAS_API_KEY, SAMBANOVA_API_KEY, or LOCAL_LLM_BASE_URL in your .env file."
            )
        else:
            logger.info(
                "Initialized LLMAuditor with %d active provider endpoint(s): %s",
                len(self.active_endpoints),
                [ep.name for ep in self.active_endpoints],
            )

    @property
    def model(self) -> str:
        """Name of the currently active primary model (for logging compatibility)."""
        if self.active_endpoints:
            return f"{self.active_endpoints[0].name} ({self.active_endpoints[0].model})"
        return "none"

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
        """Audit a batch of laptops against their raw specs using the failover chain."""
        if identifiers is None:
            identifiers = [
                laptop.get("url") or f"laptop_{idx}"
                for idx, laptop in enumerate(laptops)
            ]

        if not self.active_endpoints:
            logger.warning("No active LLM provider endpoints configured. Skipping audit.")
            return BatchAuditResponse(
                audited_laptops=[
                    ProductAuditResult(laptop_id=ident, has_contradictions=False, corrections=[])
                    for ident in identifiers
                ]
            )

        batch_payload = [
            self._prepare_laptop_payload(lap, ident)
            for lap, ident in zip(laptops, identifiers)
        ]

        prompt_text = (
            "Hi, this is the result of scraping + structuring of Egyptian laptop stores. "
            "The structured schema given to you might contain mismatches or missing values from the original scraped text "
            "represented in 'source_table', 'group_raw_specs', and 'title'. "
            "Your task is to check every single field in every laptop given to you, correct any mismatches, and fill in missing fields explicitly stated in the raw text.\n\n"
            f"INPUT_BATCH:\n{json.dumps(batch_payload, indent=2, ensure_ascii=False)}\n\n"
            "Return your response ONLY as a JSON object matching this schema:\n"
            "{\n"
            '  "audited_laptops": [\n'
            "    {\n"
            '      "laptop_id": "string",\n'
            '      "has_contradictions": boolean,\n'
            '      "corrections": [\n'
            "        {\n"
            '          "field_path": "category.subfield",\n'
            '          "current_value": any,\n'
            '          "corrected_value": any,\n'
            '          "reason": "explanation",\n'
            '          "evidence_quote": "exact verbatim quote from source"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n"
        )

        last_error = None
        for ep in self.active_endpoints:
            if ep.name in self._exhausted_endpoints:
                continue

            client = self._clients[ep.name]
            limiter = self._rate_limiters[ep.name]

            sys_prompt = AUDITOR_SYSTEM_INSTRUCTION.strip()
            if ep.is_reasoning:
                sys_prompt += "\n/no_think"

            for attempt in range(1, self.max_retries + 1):
                try:
                    limiter.wait_if_needed()

                    response = client.chat.completions.create(
                        model=ep.model,
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": prompt_text},
                        ],
                        temperature=0.0,
                        response_format={"type": "json_object"},
                    )

                    raw_text = response.choices[0].message.content or ""
                    if not raw_text:
                        raise ValueError(f"{ep.name} returned empty content")

                    cleaned = _clean_json_text(raw_text)
                    parsed_data = json.loads(cleaned)

                    # Normalize container if needed
                    if isinstance(parsed_data, list):
                        parsed_data = {"audited_laptops": parsed_data}
                    elif isinstance(parsed_data, dict) and "audited_laptops" not in parsed_data:
                        if "corrections" in parsed_data or "has_contradictions" in parsed_data:
                            parsed_data = {"audited_laptops": [parsed_data]}

                    res = BatchAuditResponse.model_validate(parsed_data)
                    logger.debug("Successfully audited batch via %s", ep.name)
                    return res

                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    is_payload_too_large = "413" in err_str or "payload too large" in err_str or "request too large" in err_str or "context_length_exceeded" in err_str
                    if is_payload_too_large and len(laptops) > 1:
                        logger.info("Batch of %d laptops too large for %s (413). Automatically splitting batch...", len(laptops), ep.name)
                        mid = len(laptops) // 2
                        res1 = self.audit_batch(laptops[:mid], identifiers[:mid])
                        res2 = self.audit_batch(laptops[mid:], identifiers[mid:])
                        return BatchAuditResponse(audited_laptops=res1.audited_laptops + res2.audited_laptops)

                    is_rate_limit = "429" in err_str or "rate_limit" in err_str or "quota" in err_str
                    is_unavailable = "503" in err_str or "unavailable" in err_str or "overloaded" in err_str

                    if is_rate_limit and ("day" in err_str or "exceeded your current quota" in err_str):
                        logger.warning("Daily quota reached on %s. Blacklisting and failing over...", ep.name)
                        self._exhausted_endpoints.add(ep.name)
                        break

                    if (is_rate_limit or is_unavailable) and attempt < self.max_retries:
                        backoff = 2.0 * attempt
                        logger.warning(
                            "Transient %s on %s (attempt %d/%d). Backing off %.1fs...",
                            "RateLimit" if is_rate_limit else "Unavailable",
                            ep.name, attempt, self.max_retries, backoff
                        )
                        time.sleep(backoff)
                        continue
                    else:
                        logger.warning("Endpoint %s failed: %s. Failing over to next provider...", ep.name, e)
                        break

        logger.error("Audit failed across all configured LLM endpoints: %s", last_error)
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
        batch_size: int = 1,
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


# Backward compatibility alias
GeminiAuditor = LLMAuditor
