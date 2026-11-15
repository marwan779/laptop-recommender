from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CacheSettings(BaseSettings):
    """Configuration for the distributed Redis cache and inbox deduplication."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_url: str = "redis://localhost:6379/0"
    cache_default_ttl_seconds: int = 86400
    redis_socket_connect_timeout_seconds: float = 2.0
    redis_socket_timeout_seconds: float = 2.0
    redis_health_check_interval_seconds: int = 30
    redis_scan_count: int = 100

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_default(cls, data: Any) -> Any:
        """Strip empty or whitespace-only environment strings so defaults apply."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not (isinstance(v, str) and v.strip() == "")}
        return data


@lru_cache(maxsize=1)
def get_cache_settings() -> CacheSettings:
    """Singleton provider for CacheSettings."""
    return CacheSettings()


__all__ = ["CacheSettings", "get_cache_settings"]
