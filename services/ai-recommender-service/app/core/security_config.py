from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseSettings):
    """Configuration for inter-service X-API-Key authentication."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ai_recommender_api_key: str = ""
    require_api_key: bool = True

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_default(cls, data: Any) -> Any:
        """Strip empty or whitespace-only environment strings so defaults apply."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not (isinstance(v, str) and v.strip() == "")}
        return data

    @property
    def api_key_configured(self) -> bool:
        """Return True when a non-blank API key is configured."""
        return bool(self.ai_recommender_api_key.strip())


@lru_cache(maxsize=1)
def get_security_settings() -> SecuritySettings:
    """Singleton provider for SecuritySettings."""
    return SecuritySettings()


__all__ = ["SecuritySettings", "get_security_settings"]
