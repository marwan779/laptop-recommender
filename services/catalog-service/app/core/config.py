from pathlib import Path
from typing import Any

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    service_name: str = "catalog-service"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/laptop_recommender_catalog"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Downstream Services
    scraper_service_url: str = "http://localhost:8001"

    # Scraping Cron Job Configuration (one-shot CLI execution)
    scraping_cron_level: int = 2
    scraping_cron_send_email: bool = True

    # Price Sync Cron Job Configuration (one-shot CLI execution)
    price_sync_batch_limit: int = 50

    # RabbitMQ Messaging Broker
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange_name: str = "laptop_events"
    rabbitmq_dlx_exchange_name: str = "laptop_events.dlx"
    rabbitmq_prefetch_count: int = 10
    rabbitmq_connection_timeout_seconds: float = 10.0

    # Redis Cache Store
    redis_url: str = "redis://localhost:6379/0"
    enable_cache: bool = True
    cache_default_ttl_seconds: int = 3600

    # Transactional Outbox Relay
    outbox_lease_duration_minutes: int = 5
    outbox_batch_size: int = 50

    model_config = SettingsConfigDict(
        env_file=(SERVICE_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_default(cls, data: Any) -> Any:
        """Strip empty or whitespace-only environment strings so defaults apply."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not (isinstance(v, str) and v.strip() == "")}
        return data

    @computed_field
    @property
    def async_database_url(self) -> str:
        """Ensure database URL uses asyncpg driver for async SQLAlchemy."""
        url = (self.database_url or "").strip()
        if not url:
            url = "postgresql+asyncpg://postgres:postgres@localhost:5432/laptop_recommender_catalog"
        if url.startswith("postgresql+psycopg://"):
            return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @computed_field
    @property
    def sync_database_url(self) -> str:
        """Ensure database URL uses psycopg driver for synchronous tools (e.g. Alembic sync fallback)."""
        url = (self.database_url or "").strip()
        if not url:
            url = "postgresql+psycopg://postgres:postgres@localhost:5432/laptop_recommender_catalog"
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


settings = Settings()
