"""Core configuration settings package for ai-recommender-service."""

from app.core.security_config import SecuritySettings, get_security_settings

__all__ = ["SecuritySettings", "get_security_settings"]
