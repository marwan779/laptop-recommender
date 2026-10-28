from pathlib import Path
from pydantic import computed_field
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

    model_config = SettingsConfigDict(
        env_file=(SERVICE_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    @property
    def async_database_url(self) -> str:
        """Ensure database URL uses asyncpg driver for async SQLAlchemy."""
        url = self.database_url
        if url.startswith("postgresql+psycopg://"):
            return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @computed_field
    @property
    def sync_database_url(self) -> str:
        """Ensure database URL uses psycopg driver for synchronous tools (e.g. Alembic sync fallback)."""
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


settings = Settings()
