"""Outbox Relay Worker for Transactional Outbox Pattern.

Polls pending OutboxMessage records using row-level locking (SKIP LOCKED),
publishes them to RabbitMQ with publisher confirms, and transitions their
lifecycle status to PUBLISHED (or FAILED on error).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.messaging.contract import IMessageBroker
from app.common.messaging.rabbitmq import RabbitMQBroker
from app.core.database import AsyncSessionLocal
from app.models.outbox import OutboxMessage
from app.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger("catalog.jobs.outbox_relay")


class OutboxRelayWorker:
    """Background relay worker that reliably publishes transactional outbox messages."""

    def __init__(
        self,
        broker: IMessageBroker | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
        poll_interval_seconds: float = 2.0,
        batch_size: int = 50,
    ) -> None:
        self.broker = broker or RabbitMQBroker()
        self._session_factory = session_factory or AsyncSessionLocal
        self.poll_interval_seconds = poll_interval_seconds
        self.batch_size = batch_size
        self._task: asyncio.Task | None = None
        self._is_running: bool = False

    async def _publish_message(self, repo: OutboxRepository, msg: OutboxMessage) -> bool:
        """Publish a single outbox message and update repository status."""
        try:
            try:
                payload = json.loads(msg.payload_json)
            except Exception:
                payload = msg.payload_json

            await self.broker.publish(
                routing_key=msg.routing_key,
                message=payload,
            )
            await repo.mark_as_dispatched(msg.id)
            logger.debug(
                "Successfully dispatched outbox message [id=%s, routing_key=%s]",
                msg.id,
                msg.routing_key,
            )
            return True
        except Exception as exc:
            logger.error(
                "Failed to dispatch outbox message [id=%s, routing_key=%s]: %s",
                msg.id,
                msg.routing_key,
                exc,
                exc_info=True,
            )
            await repo.mark_failed(msg.id, str(exc))
            return False

    async def _process_batch_with_session(self, session: AsyncSession) -> int:
        """Internal worker executing query and publish with session."""
        repo = OutboxRepository(session)
        claimed_messages = await repo.claim_batch(batch_size=self.batch_size)

        if not claimed_messages:
            return 0

        logger.info("Outbox relay claimed %d pending messages.", len(claimed_messages))

        # Ensure broker is connected before dispatching
        if not self.broker.is_connected:
            await self.broker.connect()

        for msg in claimed_messages:
            await self._publish_message(repo, msg)

        await session.flush()
        return len(claimed_messages)

    async def run_once(self, session: AsyncSession | None = None) -> int:
        """Execute a single outbox relay polling pass.

        Returns:
            The number of messages claimed and processed.
        """
        if session is not None:
            return await self._process_batch_with_session(session)

        async with self._session_factory() as sess:
            async with sess.begin():
                return await self._process_batch_with_session(sess)

    async def _relay_loop(self) -> None:
        """Continuous background execution loop."""
        logger.info(
            "Starting outbox relay worker loop (poll_interval: %.1fs, batch_size: %d)",
            self.poll_interval_seconds,
            self.batch_size,
        )
        self._is_running = True

        while self._is_running:
            try:
                processed_count = await self.run_once()
                # If we processed a full batch, poll immediately without waiting full interval
                if processed_count >= self.batch_size:
                    await asyncio.sleep(0.1)
                else:
                    await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                logger.info("Outbox relay worker loop received cancellation signal. Stopping.")
                break
            except Exception as exc:
                logger.error("Unexpected error in outbox relay loop: %s", exc, exc_info=True)
                await asyncio.sleep(self.poll_interval_seconds)

        self._is_running = False

    def start(self) -> asyncio.Task | None:
        """Start the background relay worker task."""
        if self._task and not self._task.done():
            logger.warning("Outbox relay task is already running.")
            return self._task

        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._relay_loop(), name="outbox-relay-worker")
        return self._task

    async def stop(self) -> None:
        """Gracefully stop the background worker task."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Outbox relay worker stopped.")


# Singleton instance
outbox_relay = OutboxRelayWorker()
