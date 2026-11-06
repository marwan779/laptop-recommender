"""Cache Provider Interface Contract.

Defines the abstract interface for in-memory and distributed cache providers,
enforcing Dependency Inversion (DIP), Open/Closed Principle (OCP), and
100% unit test isolation without external infrastructure dependencies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ICacheProvider(ABC):
    """Abstract contract for key-value cache providers."""

    async def connect(self) -> None:
        """Initialize connections or underlying resources (optional lifecycle hook)."""

    async def close(self) -> None:
        """Gracefully release connections and resources (optional lifecycle hook)."""

    @abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Retrieve cached bytes for a given key.

        Args:
            key: Unique cache key.

        Returns:
            Raw bytes if the key exists and has not expired, otherwise None.
        """
        ...

    @abstractmethod
    async def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> None:
        """Store raw bytes under a key with an optional Time-To-Live (TTL).

        Args:
            key: Unique cache key.
            value: Raw payload bytes to cache.
            ttl_seconds: Expiration time in seconds (None uses provider default or no expiry).
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove a specific key from the cache.

        Args:
            key: Unique cache key to evict.
        """
        ...

    @abstractmethod
    async def clear_prefix(self, prefix: str) -> int:
        """Evict all keys matching the given prefix.

        Args:
            prefix: Key prefix (e.g. 'catalog:laptop:').

        Returns:
            Number of keys evicted.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify whether the cache provider is reachable and operational.

        Returns:
            True if healthy, False otherwise.
        """
        ...
