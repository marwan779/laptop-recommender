"""In-Memory Cache Provider Implementation.

Lightweight dictionary-backed cache provider with monotonic TTL support.
Used for fast, deterministic unit/integration testing without requiring
a live Redis instance, as well as local fallback when Redis is disabled.
"""

from __future__ import annotations

import time

from app.common.cache.provider import ICacheProvider


class InMemoryCacheProvider(ICacheProvider):
    """Thread-safe asyncio in-memory key-value store with TTL expiration."""

    def __init__(self, default_ttl_seconds: int = 3600) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self._store: dict[str, tuple[bytes, float | None]] = {}
        self._healthy: bool = True

    async def connect(self) -> None:
        self._healthy = True

    async def close(self) -> None:
        self._store.clear()
        self._healthy = False

    def _get_live_entry(self, key: str) -> tuple[bytes, float | None] | None:
        """Return a non-expired store entry, evicting it lazily when stale."""
        entry = self._store.get(key)
        if entry is None:
            return None

        _value, expires_at = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None

        return entry

    async def get(self, key: str) -> bytes | None:
        if not self._healthy:
            return None

        entry = self._get_live_entry(key)
        if entry is None:
            return None
        return entry[0]

    async def set(self, key: str, value: bytes | str, ttl_seconds: int | None = None) -> None:
        if not self._healthy:
            return

        raw_bytes = value.encode("utf-8") if isinstance(value, str) else value
        effective_ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds

        expires_at: float | None = None
        if effective_ttl and effective_ttl > 0:
            expires_at = time.monotonic() + effective_ttl

        self._store[key] = (raw_bytes, expires_at)

    async def set_nx(self, key: str, value: bytes | str, ttl_seconds: int = 86400) -> bool:
        """Atomically claim a key; returns False when an unexpired entry already exists."""
        if not self._healthy:
            # Fail-open: allow processing when the cache is unavailable.
            return True

        if self._get_live_entry(key) is not None:
            return False

        await self.set(key, value, ttl_seconds=ttl_seconds)
        return True

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear_prefix(self, prefix: str) -> int:
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            self._store.pop(k, None)
        return len(keys_to_delete)

    async def health_check(self) -> bool:
        return self._healthy
