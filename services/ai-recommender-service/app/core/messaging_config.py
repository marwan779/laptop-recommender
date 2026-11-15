from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class RabbitMQSettings(BaseSettings):
    """Configuration for RabbitMQ messaging broker and event topology."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange_name: str = "laptop_events"
    rabbitmq_dlx_exchange_name: str = "laptop_events.dlx"
    rabbitmq_prefetch_count: int = 10
    rabbitmq_connection_timeout_seconds: float = 10.0


@lru_cache(maxsize=1)
def get_rabbitmq_settings() -> RabbitMQSettings:
    """Singleton provider for RabbitMQSettings."""
    return RabbitMQSettings()
