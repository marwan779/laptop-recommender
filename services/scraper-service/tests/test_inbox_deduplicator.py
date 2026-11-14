"""Unit tests for the distributed Redis inbox deduplicator."""

import pytest

from app.common.cache import InMemoryCacheProvider
from app.common.messaging.inbox import RedisInboxDeduplicator


@pytest.fixture
def inbox():
    cache = InMemoryCacheProvider(default_ttl_seconds=60)
    return RedisInboxDeduplicator(cache, default_ttl_seconds=60)


@pytest.mark.anyio
async def test_claim_message_is_idempotent(inbox):
    assert await inbox.claim_message("msg-1", "catalog.scrape.command") is True
    assert await inbox.claim_message("msg-1", "catalog.scrape.command") is False


@pytest.mark.anyio
async def test_mark_completed_keeps_message_deduplicated(inbox):
    assert await inbox.claim_message("msg-2", "prices.check.command") is True
    await inbox.mark_completed("msg-2")

    assert await inbox.cache.get("inbox:msg-2") == b"COMPLETED"
    assert await inbox.claim_message("msg-2", "prices.check.command") is False


@pytest.mark.anyio
async def test_release_claim_allows_retry(inbox):
    assert await inbox.claim_message("msg-3", "reviews.scrape.command") is True
    await inbox.release_claim("msg-3")

    assert await inbox.cache.get("inbox:msg-3") is None
    assert await inbox.claim_message("msg-3", "reviews.scrape.command") is True


@pytest.mark.anyio
async def test_different_message_ids_are_independent(inbox):
    assert await inbox.claim_message("msg-4", "catalog.scrape.command") is True
    assert await inbox.claim_message("msg-5", "catalog.scrape.command") is True
