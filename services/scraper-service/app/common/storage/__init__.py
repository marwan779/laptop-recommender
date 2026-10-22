"""Object Storage abstraction and providers for laptop-recommender scraper service."""

from app.common.storage.base import IObjectStorageService
from app.common.storage.exceptions import (
    StorageConnectionError,
    StorageError,
    StorageNotFoundError,
    StorageOperationError,
    StoragePermissionError,
)
from app.common.storage.factory import StorageFactory, get_storage_service
from app.common.storage.models import (
    BatchDeleteResult,
    ObjectMetadata,
    ObjectSummary,
    StorageObject,
)
from app.common.storage.s3 import S3StorageService

__all__ = [
    "IObjectStorageService",
    "S3StorageService",
    "StorageFactory",
    "get_storage_service",
    "StorageObject",
    "ObjectMetadata",
    "ObjectSummary",
    "BatchDeleteResult",
    "StorageError",
    "StorageNotFoundError",
    "StoragePermissionError",
    "StorageConnectionError",
    "StorageOperationError",
]
