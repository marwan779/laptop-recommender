"""Tests for RabbitMQ messaging infrastructure and Redis inbox deduplication."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aio_pika
import pytest
from pydantic import BaseModel

from app.common.cache import InMemoryCacheProvider
from app.common.messaging import (
    IMessageBroker,
    RabbitMQBroker,
    RedisInboxDeduplicator,
)
from app.core.messaging_config import RabbitMQSettings


class _FakeProcess:
    def __init__(self, message: "_FakeIncomingMessage") -> None:
        self._message = message

    async def __aenter__(self) -> "_FakeProcess":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self._message.nacked = exc_type is not None
        return False


class _FakeIncomingMessage:
    def __init__(self, payload: dict[str, Any] | None = None, message_id: str = "msg-1", raw: bytes | None = None) -> None:
        self.body = raw if raw is not None else json.dumps(payload or {}).encode("utf-8")
        self.message_id = message_id
        self.nacked = False
        self.process_calls: list[dict[str, Any]] = []

    def process(self, requeue: bool, ignore_processed: bool) -> _FakeProcess:
        self.process_calls.append({"requeue": requeue, "ignore_processed": ignore_processed})
        return _FakeProcess(self)


class _FakeExchange:
    def __init__(self, name: str, exchange_type: Any, durable: bool) -> None:
        self.name = name
        self.type = exchange_type
        self.durable = durable
        self.published: list[tuple[Any, str]] = []

    async def publish(self, message: Any, routing_key: str) -> None:
        self.published.append((message, routing_key))


class _FakeQueue:
    def __init__(self, name: str, durable: bool, arguments: dict[str, Any] | None = None) -> None:
        self.name = name
        self.durable = durable
        self.arguments = arguments
        self.bound: list[tuple[str, str]] = []
        self.consumer = None

    async def bind(self, exchange: _FakeExchange, routing_key: str) -> None:
        self.bound.append((exchange.name, routing_key))

    async def consume(self, callback) -> None:
        self.consumer = callback


class _FakeChannel:
    def __init__(self) -> None:
        self.is_closed = False
        self.qos_calls: list[int] = []
        self.exchanges_declared: list[dict[str, Any]] = []
        self.queues_declared: list[dict[str, Any]] = []
        self.exchanges: dict[str, _FakeExchange] = {}
        self.queues: dict[str, _FakeQueue] = {}

    async def set_qos(self, prefetch_count: int) -> None:
        self.qos_calls.append(prefetch_count)

    async def declare_exchange(self, name: str, type: Any, durable: bool) -> _FakeExchange:
        self.exchanges_declared.append({"name": name, "type": type, "durable": durable})
        exchange = _FakeExchange(name, type, durable)
        self.exchanges[name] = exchange
        return exchange

    async def declare_queue(self, name: str, durable: bool, arguments: dict[str, Any] | None = None) -> _FakeQueue:
        self.queues_declared.append({"name": name, "durable": durable, "arguments": arguments})
        queue = _FakeQueue(name, durable, arguments)
        self.queues[name] = queue
        return queue

    async def close(self) -> None:
        self.is_closed = True


class _FakeConnection:
    def __init__(self) -> None:
        self.is_closed = False
        self.channel_obj = _FakeChannel()
        self.channel_calls: list[dict[str, Any]] = []

    async def channel(self, **kwargs: Any) -> _FakeChannel:
        self.channel_calls.append(kwargs)
        return self.channel_obj

    async def close(self) -> None:
        self.is_closed = True


def _make_broker(monkeypatch: pytest.MonkeyPatch) -> tuple[RabbitMQBroker, _FakeConnection, _FakeChannel]:
    connection = _FakeConnection()
    connect_calls: list[dict[str, Any]] = []

    async def fake_connect_robust(url: str, **kwargs: Any) -> _FakeConnection:
        connect_calls.append({"url": url, **kwargs})
        return connection

    monkeypatch.setattr(aio_pika, "connect_robust", fake_connect_robust)
    broker = RabbitMQBroker(settings=RabbitMQSettings())
    broker._connect_calls = connect_calls  # type: ignore[attr-defined]
    return broker, connection, connection.channel_obj


def test_redis_inbox_deduplicator_claim_complete_release_and_prefix() -> None:
    async def scenario() -> None:
        cache = InMemoryCacheProvider()
        inbox = RedisInboxDeduplicator(cache)
        assert isinstance(inbox, RedisInboxDeduplicator)

        assert await inbox.claim_message("evt-1", "reviews.ready.event") is True
        assert await cache.get("ai:inbox:evt-1") == b"PROCESSING"

        assert await inbox.claim_message("evt-1", "reviews.ready.event") is False

        await inbox.mark_completed("evt-1")
        assert await cache.get("ai:inbox:evt-1") == b"COMPLETED"
        assert await inbox.claim_message("evt-1", "reviews.ready.event") is False

        await inbox.release_claim("evt-1")
        assert await cache.get("ai:inbox:evt-1") is None
        assert await inbox.claim_message("evt-1", "reviews.ready.event") is True

        custom = RedisInboxDeduplicator(cache, key_prefix="custom:inbox")
        assert await custom.claim_message("evt-1", "reviews.ready.event") is True
        assert await cache.get("custom:inbox:evt-1") == b"PROCESSING"
        assert await cache.get("inbox:evt-1") is None

    asyncio.run(scenario())


def test_rabbitmq_publish_requires_connection_and_serializes_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Event(BaseModel):
        event_id: str
        correlation_id: str
        name: str

    async def scenario() -> None:
        broker, connection, channel = _make_broker(monkeypatch)
        assert isinstance(broker, IMessageBroker)
        assert broker.is_connected is False

        with pytest.raises(RuntimeError, match="not connected"):
            await broker.publish("reviews.ready.event", {})

        await broker.connect()
        assert broker.is_connected is True
        assert connection.channel_calls == [{"publisher_confirms": True}]
        assert channel.qos_calls == [10]
        assert [item["name"] for item in channel.exchanges_declared] == [
            "laptop_events.dlx",
            "laptop_events",
        ]
        assert all(item["type"] == aio_pika.ExchangeType.TOPIC for item in channel.exchanges_declared)
        assert all(item["durable"] is True for item in channel.exchanges_declared)

        with pytest.raises(TypeError, match="Unsupported message type"):
            await broker.publish("reviews.ready.event", "not-a-model")  # type: ignore[arg-type]

        event = _Event(event_id="evt-1", correlation_id="corr-1", name="reviews.ready")
        await broker.publish("reviews.ready.event", event)
        exchange = channel.exchanges["laptop_events"]
        amqp_message, routing_key = exchange.published[-1]
        assert routing_key == "reviews.ready.event"
        assert amqp_message.body == event.model_dump_json().encode("utf-8")
        assert amqp_message.content_type == "application/json"
        assert amqp_message.content_encoding == "utf-8"
        assert amqp_message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
        assert amqp_message.correlation_id == "corr-1"
        assert amqp_message.message_id == "evt-1"

        await broker.publish(
            "reviews.ready.event",
            {"event_id": "evt-2", "correlation_id": "corr-2", "payload": {"ok": True}},
        )
        dict_message, dict_routing_key = exchange.published[-1]
        assert dict_routing_key == "reviews.ready.event"
        assert json.loads(dict_message.body) == {
            "event_id": "evt-2",
            "correlation_id": "corr-2",
            "payload": {"ok": True},
        }
        assert dict_message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
        assert dict_message.correlation_id == "corr-2"
        assert dict_message.message_id == "evt-2"

    asyncio.run(scenario())


def test_rabbitmq_subscribe_topology_and_safe_consumer(monkeypatch: pytest.MonkeyPatch) -> None:
    handled: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        handled.append(payload)

    async def failing_handler(payload: dict[str, Any]) -> None:
        raise ValueError(f"handler failed for {payload['id']}")

    async def scenario() -> None:
        broker, _connection, channel = _make_broker(monkeypatch)
        with pytest.raises(RuntimeError, match="not connected"):
            await broker.subscribe("queue", "rk", handler)

        await broker.connect()
        await broker.subscribe(
            "ai.reviews.queue",
            "reviews.ready.event",
            handler,
            prefetch_count=3,
        )

        assert channel.qos_calls[-1] == 3
        assert [item["name"] for item in channel.queues_declared] == [
            "ai.reviews.queue.dlq",
            "ai.reviews.queue",
        ]
        dlq = channel.queues["ai.reviews.queue.dlq"]
        primary = channel.queues["ai.reviews.queue"]
        assert dlq.durable is True
        assert dlq.bound == [("laptop_events.dlx", "dlq.ai.reviews.queue")]
        assert primary.durable is True
        assert primary.arguments == {
            "x-dead-letter-exchange": "laptop_events.dlx",
            "x-dead-letter-routing-key": "dlq.ai.reviews.queue",
        }
        assert primary.bound == [("laptop_events", "reviews.ready.event")]
        assert primary.consumer is not None

        ok_message = _FakeIncomingMessage({"id": "ok"}, message_id="msg-ok")
        await primary.consumer(ok_message)
        assert handled == [{"id": "ok"}]
        assert ok_message.process_calls == [{"requeue": False, "ignore_processed": True}]
        assert ok_message.nacked is False

        await broker.subscribe(
            "ai.reviews.failed",
            "reviews.failed",
            failing_handler,
            prefetch_count=1,
        )
        failed_queue = channel.queues["ai.reviews.failed"]
        bad_message = _FakeIncomingMessage({"id": "bad"}, message_id="msg-bad")

        with pytest.raises(ValueError, match="handler failed for bad"):
            await failed_queue.consumer(bad_message)

        assert bad_message.process_calls == [{"requeue": False, "ignore_processed": True}]
        assert bad_message.nacked is True

    asyncio.run(scenario())


def test_rabbitmq_close_resets_connection_and_exchange_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        broker, connection, channel = _make_broker(monkeypatch)
        await broker.connect()
        assert broker._exchanges
        assert broker._default_exchange is not None
        assert broker._dlx_exchange is not None

        await broker.close()

        assert broker.is_connected is False
        assert broker._connection is None
        assert broker._channel is None
        assert broker._exchanges == {}
        assert broker._default_exchange is None
        assert broker._dlx_exchange is None
        assert channel.is_closed is True
        assert connection.is_closed is True

    asyncio.run(scenario())
