"""Distributed Redis Inbox Deduplicator.

Protects scraper-side command handlers from duplicate execution storms using
the atomic ``SET NX EX`` primitive on the shared cache provider. The inbox is
process-independent, so multiple scraper replicas observing the same broker
message will race on a single key and only one will claim the work.
"""

from __future__ import annotations

from app.common.cache.provider import ICacheProvider
from app.common.logger import get_logger

logger = get_logger("scraper.common.messaging.inbox")

_KEY_PREFIX = "inbox"
_CLAIMED_VALUE = b"PROCESSING"
_COMPLETED_VALUE = b"COMPLETED"


class RedisInboxDeduplicator:
    """Cache-backed idempotency gate for incoming broker messages."""

    def __init__(self, cache: ICacheProvider, default_ttl_seconds: int = 86400) -> None:
        self.cache = cache
        self.default_ttl_seconds = default_ttl_seconds

    @staticmethod
    def _key(message_id: str) -> str:
        return f"{_KEY_PREFIX}:{message_id}"

    async def claim_message(
        self,
        message_id: str,
        event_type: str,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Atomically claim a message for processing.

        Returns:
            True when this caller owns the claim, False when the message is
            already being processed or has already completed.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        claimed = await self.cache.set_nx(self._key(message_id), _CLAIMED_VALUE, ttl_seconds=ttl)
        if claimed:
            logger.debug("Claimed inbox message [%s, event_type=%s]", message_id, event_type)
        return claimed

    async def mark_completed(self, message_id: str, ttl_seconds: int | None = None) -> None:
        """Mark a claimed message as successfully processed, retaining the TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        await self.cache.set(self._key(message_id), _COMPLETED_VALUE, ttl_seconds=ttl)

    async def release_claim(self, message_id: str) -> None:
        """Release an in-flight claim so a failed message can be retried."""
        await self.cache.delete(self._key(message_id))


__all__ = ["RedisInboxDeduplicator"]
