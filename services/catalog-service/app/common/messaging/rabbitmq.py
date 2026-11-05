"""RabbitMQ concrete implementation using aio-pika.

Provides robust connections, topic exchange topologies, automated Dead Letter
Exchanges (DLX), persistent delivery, and safe message processing lifecycle.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import json
import logging
from typing import Any
import uuid

import aio_pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractExchange,
    AbstractIncomingMessage,
)
from pydantic import BaseModel

from app.common.messaging.contract import IMessageBroker
from app.core.messaging_config import RabbitMQSettings, get_rabbitmq_settings

logger = logging.getLogger("catalog.messaging.rabbitmq")


class RabbitMQBroker(IMessageBroker):
    """Production RabbitMQ broker client built on aio-pika."""

    def __init__(self, settings: RabbitMQSettings | None = None) -> None:
        self.settings = settings or get_rabbitmq_settings()
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None
        self._default_exchange: AbstractExchange | None = None
        self._dlx_exchange: AbstractExchange | None = None
        self._exchanges: dict[str, AbstractExchange] = {}

    @property
    def is_connected(self) -> bool:
        """Return True if connection and channel are open and ready."""
        return bool(
            self._connection and not self._connection.is_closed and self._channel and not self._channel.is_closed
        )

    async def connect(self) -> None:
        """Establish robust connection, declare DLX and primary exchanges."""
        if self.is_connected:
            return

        logger.info("Connecting to RabbitMQ at %s", self.settings.rabbitmq_url.split("@")[-1])
        self._connection = await aio_pika.connect_robust(
            self.settings.rabbitmq_url,
            timeout=self.settings.rabbitmq_connection_timeout_seconds,
        )
        self._channel = await self._connection.channel(publisher_confirms=True)
        await self._channel.set_qos(prefetch_count=self.settings.rabbitmq_prefetch_count)

        # 1. Declare Dead Letter Exchange (DLX)
        self._dlx_exchange = await self._channel.declare_exchange(
            name=self.settings.rabbitmq_dlx_exchange_name,
            type=aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        self._exchanges[self.settings.rabbitmq_dlx_exchange_name] = self._dlx_exchange

        # 2. Declare Primary Domain Topic Exchange
        self._default_exchange = await self._channel.declare_exchange(
            name=self.settings.rabbitmq_exchange_name,
            type=aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        self._exchanges[self.settings.rabbitmq_exchange_name] = self._default_exchange

        logger.info(
            "RabbitMQ connected. Exchanges ready: primary='%s', dlx='%s'",
            self.settings.rabbitmq_exchange_name,
            self.settings.rabbitmq_dlx_exchange_name,
        )

    async def close(self) -> None:
        """Gracefully close channel and connection."""
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
            self._channel = None

        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            self._connection = None

        self._exchanges.clear()
        self._default_exchange = None
        self._dlx_exchange = None
        logger.info("RabbitMQ connection closed gracefully.")

    async def _get_or_declare_exchange(self, exchange_name: str | None = None) -> AbstractExchange:
        """Retrieve cached exchange or declare dynamically if unknown."""
        target_name = exchange_name or self.settings.rabbitmq_exchange_name
        if not self._channel or self._channel.is_closed:
            raise RuntimeError("Cannot declare exchange: channel is closed or broker not connected.")

        if target_name in self._exchanges:
            return self._exchanges[target_name]

        exchange = await self._channel.declare_exchange(
            name=target_name,
            type=aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        self._exchanges[target_name] = exchange
        return exchange

    async def publish(
        self,
        routing_key: str,
        message: BaseModel | dict[str, Any],
        exchange_name: str | None = None,
    ) -> None:
        """Publish a persistent message with publisher confirmation."""
        if not self.is_connected:
            raise RuntimeError("Broker is not connected. Call connect() before publishing.")

        exchange = await self._get_or_declare_exchange(exchange_name)

        if isinstance(message, BaseModel):
            body_bytes = message.model_dump_json().encode("utf-8")
            correlation_id = getattr(message, "correlation_id", None) or str(uuid.uuid4())
            message_id = getattr(message, "event_id", None) or str(uuid.uuid4())
        elif isinstance(message, dict):
            body_bytes = json.dumps(message, default=str).encode("utf-8")
            correlation_id = str(message.get("correlation_id", uuid.uuid4()))
            message_id = str(message.get("event_id", uuid.uuid4()))
        else:
            raise TypeError(f"Unsupported message type: {type(message)}. Must be BaseModel or dict.")

        amqp_message = aio_pika.Message(
            body=body_bytes,
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            correlation_id=correlation_id,
            message_id=message_id,
            timestamp=datetime.now(UTC),
        )

        await exchange.publish(amqp_message, routing_key=routing_key)
        logger.debug(
            "Published event [id=%s, routing_key=%s, correlation=%s] to exchange '%s'",
            message_id,
            routing_key,
            correlation_id,
            exchange.name,
        )

    async def subscribe(
        self,
        queue_name: str,
        routing_key: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        exchange_name: str | None = None,
        prefetch_count: int | None = None,
    ) -> None:
        """Declare queue with DLQ routing, bind, and register safe consumer handler."""
        if not self.is_connected or self._channel is None:
            raise RuntimeError("Broker is not connected. Call connect() before subscribing.")

        exchange = await self._get_or_declare_exchange(exchange_name)

        if prefetch_count:
            await self._channel.set_qos(prefetch_count=prefetch_count)

        # 1. Declare companion Dead Letter Queue (DLQ)
        dlq_name = f"{queue_name}.dlq"
        dlq = await self._channel.declare_queue(name=dlq_name, durable=True)
        if self._dlx_exchange:
            await dlq.bind(self._dlx_exchange, routing_key=f"dlq.{queue_name}")

        # 2. Declare primary queue with DLX arguments
        queue = await self._channel.declare_queue(
            name=queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": self.settings.rabbitmq_dlx_exchange_name,
                "x-dead-letter-routing-key": f"dlq.{queue_name}",
            },
        )

        # 3. Bind primary queue to the exchange
        await queue.bind(exchange, routing_key=routing_key)

        # 4. Define safe message processor wrapper
        async def _message_consumer(incoming_msg: AbstractIncomingMessage) -> None:
            async with incoming_msg.process(requeue=False, ignore_processed=True):
                try:
                    payload = json.loads(incoming_msg.body.decode("utf-8"))
                    await handler(payload)
                except Exception as exc:
                    logger.error(
                        "Consumer handler failed on queue '%s' [msg_id=%s]: %s. Routing to DLQ.",
                        queue_name,
                        incoming_msg.message_id,
                        exc,
                        exc_info=True,
                    )
                    raise  # incoming_msg.process() catches this and nacks to DLQ

        await queue.consume(_message_consumer)
        logger.info(
            "Subscribed queue '%s' to exchange '%s' [routing_key='%s']",
            queue_name,
            exchange.name,
            routing_key,
        )
