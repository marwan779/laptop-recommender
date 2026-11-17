"""Configuration for the SovereignEG dual-source extraction pipeline.

This module is the single source of truth for the LLM credentials, model
chain, and micro-batch tuning knobs used by Pipeline B. It reads only from
the environment so the values can be overridden in any deployment target.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_SERVICE_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

DEFAULT_BASE_URL = "https://backend.sovereigneg.com/v1"
DEFAULT_PRIMARY_MODEL = "claude-haiku-5.5"
DEFAULT_FALLBACK_MODEL = "gpt-oss-120b"
DEFAULT_BATCH_THRESHOLD = 80
DEFAULT_MICRO_BATCH_SIZE = 1
DEFAULT_MAX_CONCURRENCY = 4


def _env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        parsed = int(raw.strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


@dataclass(frozen=True)
class SovereignConfig:
    """Runtime configuration for the SovereignEG extraction client."""

    base_url: str = DEFAULT_BASE_URL
    primary_api_key: str = ""
    fallback_api_key: str = ""
    primary_model: str = DEFAULT_PRIMARY_MODEL
    fallback_model: str = DEFAULT_FALLBACK_MODEL
    batch_threshold: int = DEFAULT_BATCH_THRESHOLD
    micro_batch_size: int = DEFAULT_MICRO_BATCH_SIZE
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    timeout_seconds: float = 45.0
    max_transient_retries: int = 2
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> SovereignConfig:
        """Build a configuration from environment variables with safe defaults."""
        if _SERVICE_ENV_FILE.is_file():
            load_dotenv(_SERVICE_ENV_FILE, override=False)
        base_url = _env_str("ENRICHER_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        return cls(
            base_url=base_url,
            primary_api_key=_env_str("ENRICHER_LLM_API_KEY"),
            fallback_api_key=_env_str("ENRICHER_LLM_FALLBACK_API_KEY"),
            primary_model=_env_str("ENRICHER_PRIMARY_MODEL", DEFAULT_PRIMARY_MODEL) or DEFAULT_PRIMARY_MODEL,
            fallback_model=_env_str("ENRICHER_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL) or DEFAULT_FALLBACK_MODEL,
            batch_threshold=_env_int(
                "LLM_FULL_EXTRACT_BATCH_THRESHOLD",
                DEFAULT_BATCH_THRESHOLD,
                minimum=0,
                maximum=1_000_000,
            ),
            micro_batch_size=_env_int(
                "SOVEREIGN_EXTRACT_MICRO_BATCH_SIZE",
                DEFAULT_MICRO_BATCH_SIZE,
                minimum=1,
                maximum=5,
            ),
            max_concurrency=_env_int(
                "SOVEREIGN_EXTRACT_MAX_CONCURRENCY",
                DEFAULT_MAX_CONCURRENCY,
                minimum=1,
                maximum=8,
            ),
        )

    def ordered_api_keys(self) -> list[tuple[str, str]]:
        """Return configured keys in failover order, omitting empty slots."""
        keys: list[tuple[str, str]] = []
        if self.primary_api_key.strip():
            keys.append(("primary", self.primary_api_key.strip()))
        if self.fallback_api_key.strip():
            keys.append(("fallback", self.fallback_api_key.strip()))
        return keys

    def has_configured_key(self) -> bool:
        """True when a base URL and at least one API key are available."""
        return bool(self.base_url.strip()) and bool(self.ordered_api_keys())

    def chat_completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"


__all__ = [
    "DEFAULT_BATCH_THRESHOLD",
    "DEFAULT_MAX_CONCURRENCY",
    "DEFAULT_MICRO_BATCH_SIZE",
    "SovereignConfig",
]
