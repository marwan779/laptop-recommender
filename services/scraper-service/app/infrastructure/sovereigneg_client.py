"""SovereignEG OpenAI-compatible client with dual-key credit failover.

Run-scoped failover state is held by :class:`SovereignKeyManager`, which is
thread-safe and shared across every micro-batch in one pipeline run. The client
never logs or returns raw API keys.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.common.logger import get_logger
from app.core.sovereign_config import SovereignConfig

logger = get_logger("infrastructure.sovereigneg")

_CREDIT_KEYWORDS = (
    "insufficient",
    "credit",
    "credits",
    "balance",
    "quota",
    "billing",
    "payment",
    "limit exceeded",
    "depleted",
    "expired",
)
_TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}
_CREDIT_HTTP_STATUSES = {401, 402, 403}


def _classify_error(status_code: int | None, body: str) -> str:
    """Classify an HTTP/API failure as credit exhaustion, transient, or fatal."""
    lowered = (body or "").lower()
    if status_code in _CREDIT_HTTP_STATUSES:
        return "credit"
    if any(keyword in lowered for keyword in _CREDIT_KEYWORDS):
        return "credit"
    if status_code in _TRANSIENT_HTTP_STATUSES:
        return "transient"
    return "fatal"


def _strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = _strip_json_fences(text)
    for candidate in (cleaned, *re.findall(r"\{.*\}", cleaned, re.DOTALL)):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


@dataclass
class CallTelemetry:
    """Observability record for one logical extraction call."""

    model_used: str | None = None
    key_slot_used: str | None = None
    primary_key_exhausted: bool = False
    fallback_key_exhausted: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_sec: float = 0.0
    error: str | None = None
    attempts: int = 0
    model_attempts: list[str] = field(default_factory=list)


class SovereignKeyManager:
    """Thread-safe run-scoped key exhaustion tracker."""

    def __init__(self, ordered_keys: list[tuple[str, str]]) -> None:
        self._lock = threading.Lock()
        self._ordered_keys = [(slot, key) for slot, key in ordered_keys if key]
        self._exhausted_slots: set[str] = set()
        self.primary_key_exhausted = False
        self.fallback_key_exhausted = False

    def available_keys(self) -> list[tuple[str, str]]:
        with self._lock:
            return [(slot, key) for slot, key in self._ordered_keys if slot not in self._exhausted_slots]

    def mark_exhausted(self, slot: str) -> None:
        with self._lock:
            if slot in self._exhausted_slots:
                return
            self._exhausted_slots.add(slot)
            if slot == "primary":
                self.primary_key_exhausted = True
            elif slot == "fallback":
                self.fallback_key_exhausted = True
        logger.warning(
            "[SovereignEG] API key slot '%s' exhausted for the remainder of this run; failing over.",
            slot,
        )

    def snapshot(self) -> tuple[bool, bool]:
        with self._lock:
            return self.primary_key_exhausted, self.fallback_key_exhausted


class SovereignEGClient:
    """OpenAI-compatible JSON completion client with key and model failover."""

    def __init__(
        self,
        config: SovereignConfig | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config or SovereignConfig.from_env()
        self._http = http_client or httpx.Client(timeout=self.config.timeout_seconds)
        self.key_manager = SovereignKeyManager(self.config.ordered_api_keys())
        self._backoff = (1.0, 2.5)

    # ── public API ──────────────────────────────────────────────────────

    def complete_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> tuple[dict[str, Any] | None, CallTelemetry]:
        """Run the model failover chain and return ``(parsed_json, telemetry)``."""
        telemetry = CallTelemetry()
        started = time.perf_counter()

        models = [self.config.primary_model]
        if self.config.fallback_model and self.config.fallback_model != self.config.primary_model:
            models.append(self.config.fallback_model)

        for model in models:
            telemetry.model_attempts.append(model)
            parsed, telemetry = self._try_model(model, messages, temperature, max_tokens, telemetry)
            if parsed is not None:
                telemetry.model_used = model
                telemetry.latency_sec = round(time.perf_counter() - started, 3)
                primary, fallback = self.key_manager.snapshot()
                telemetry.primary_key_exhausted = primary
                telemetry.fallback_key_exhausted = fallback
                return parsed, telemetry
            logger.warning("[SovereignEG] Model '%s' failed; trying next model if available.", model)

        telemetry.latency_sec = round(time.perf_counter() - started, 3)
        primary, fallback = self.key_manager.snapshot()
        telemetry.primary_key_exhausted = primary
        telemetry.fallback_key_exhausted = fallback
        if telemetry.error is None:
            telemetry.error = "all_models_and_keys_failed"
        return None, telemetry

    # ── internals ───────────────────────────────────────────────────────

    def _try_model(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        telemetry: CallTelemetry,
    ) -> tuple[dict[str, Any] | None, CallTelemetry]:
        keys = self.key_manager.available_keys()
        if not keys:
            telemetry.error = "no_available_api_keys"
            return None, telemetry

        for slot, api_key in keys:
            parsed, telemetry = self._request_with_retries(
                slot,
                api_key,
                model,
                messages,
                temperature,
                max_tokens,
                telemetry,
            )
            if parsed is not None:
                telemetry.key_slot_used = slot
                return parsed, telemetry
            if slot not in {s for s, _ in self.key_manager.available_keys()}:
                # Key was marked exhausted; move on to the next slot immediately.
                continue

        return None, telemetry

    def _request_with_retries(
        self,
        slot: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        telemetry: CallTelemetry,
    ) -> tuple[dict[str, Any] | None, CallTelemetry]:
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        last_error: str | None = None
        for attempt in range(self.config.max_transient_retries + 1):
            telemetry.attempts += 1
            try:
                response = self._http.post(
                    self.config.chat_completions_url(),
                    headers=headers,
                    json=body,
                    timeout=self.config.timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"transport_error:{type(exc).__name__}"
                if attempt < self.config.max_transient_retries:
                    time.sleep(self._backoff[min(attempt, len(self._backoff) - 1)])
                    continue
                telemetry.error = last_error
                return None, telemetry

            if response.status_code >= 400:
                text = response.text or ""
                category = _classify_error(response.status_code, text)
                last_error = f"http_{response.status_code}:{category}"
                telemetry.error = last_error
                if category == "credit":
                    self.key_manager.mark_exhausted(slot)
                    return None, telemetry
                if category == "transient" and attempt < self.config.max_transient_retries:
                    time.sleep(self._backoff[min(attempt, len(self._backoff) - 1)])
                    continue
                return None, telemetry

            try:
                payload = response.json()
            except ValueError:
                telemetry.error = "invalid_response_json"
                return None, telemetry

            usage = payload.get("usage") or {}
            telemetry.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            telemetry.completion_tokens += int(usage.get("completion_tokens") or 0)

            content = ""
            choices = payload.get("choices") or []
            if choices and isinstance(choices[0], dict):
                message = choices[0].get("message") or {}
                content = str(message.get("content") or "")

            parsed = _parse_json_object(content)
            if parsed is None:
                telemetry.error = "invalid_model_json"
                return None, telemetry
            return parsed, telemetry

        telemetry.error = last_error or "unknown_error"
        return None, telemetry


__all__ = [
    "CallTelemetry",
    "SovereignEGClient",
    "SovereignKeyManager",
]
