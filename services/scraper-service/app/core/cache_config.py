from functools import lru_cache
from pathlib import Path

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


@lru_cache(maxsize=1)
def get_cache_settings() -> CacheSettings:
    """Singleton provider for CacheSettings."""
    return CacheSettings()
