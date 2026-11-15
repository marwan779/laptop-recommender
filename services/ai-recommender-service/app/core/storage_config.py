from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    """Configuration for Object Storage (AWS S3 & S3-Compatible providers like MinIO/LocalStack)."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Active storage provider: "s3"
    storage_provider: str = "s3"

    # AWS Credentials & Region
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "eu-central-1"

    # Default Target S3 Bucket
    aws_s3_bucket: str = "laptop-recommender-raw-catalog"

    # Custom Endpoint URL (for LocalStack, MinIO, or Cloudflare R2)
    aws_s3_endpoint_url: str | None = None

    # Connection security
    aws_s3_use_ssl: bool = True

    # Path-style addressing (required for MinIO/LocalStack where bucket is in path rather than subdomain)
    aws_s3_force_path_style: bool = False

    @property
    def is_configured(self) -> bool:
        """Return True if bucket and credentials (or custom local endpoint) are present."""
        has_bucket = bool(self.aws_s3_bucket.strip())
        has_credentials = bool(self.aws_access_key_id.strip() and self.aws_secret_access_key.strip())
        is_local_endpoint = bool(self.aws_s3_endpoint_url and self.aws_s3_endpoint_url.strip())
        return has_bucket and (has_credentials or is_local_endpoint)


@lru_cache(maxsize=1)
def get_storage_settings() -> StorageSettings:
    """Singleton provider for StorageSettings."""
    return StorageSettings()
