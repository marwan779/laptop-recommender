from functools import lru_cache
from typing import Any, Type

from app.core.storage_config import StorageSettings, get_storage_settings
from app.storage.base import IObjectStorageService
from app.storage.s3 import S3StorageService


class StorageFactory:
    """Factory for creating and resolving object storage provider instances.

    Adheres to the Open/Closed Principle (OCP) by allowing runtime registration
    of new storage providers (MinIO, GCS, Azure, Local) without modifying factory core.
    """

    _registry: dict[str, Type[IObjectStorageService]] = {
        "s3": S3StorageService,
        "aws": S3StorageService,
        "aws_s3": S3StorageService,
    }

    @classmethod
    def register_provider(cls, name: str, provider_cls: Type[IObjectStorageService]) -> None:
        """Register a new storage provider driver dynamically."""
        cls._registry[name.strip().lower()] = provider_cls

    @classmethod
    def create(
        cls,
        settings: StorageSettings | None = None,
        boto3_client: Any | None = None,
    ) -> IObjectStorageService:
        """Instantiate the active storage service based on configuration."""
        cfg = settings or get_storage_settings()
        provider_key = cfg.storage_provider.strip().lower()

        provider_cls = cls._registry.get(provider_key)
        if not provider_cls:
            supported = list(cls._registry.keys())
            raise ValueError(
                f"Unsupported storage provider '{cfg.storage_provider}'. "
                f"Supported providers: {supported}"
            )

        if issubclass(provider_cls, S3StorageService):
            return provider_cls(settings=cfg, boto3_client=boto3_client)

        return provider_cls()


@lru_cache(maxsize=1)
def get_storage_service() -> IObjectStorageService:
    """Singleton accessor for the default object storage provider."""
    return StorageFactory.create()
