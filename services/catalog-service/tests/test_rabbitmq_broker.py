"""Unit tests for RabbitMQBroker implementation in catalog-service using mocked aio-pika."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.common.messaging.rabbitmq import RabbitMQBroker
from app.core.messaging_config import RabbitMQSettings
from app.schemas.events import EventType, ScrapeCatalogCommand, ScrapeCatalogPayload


@pytest.fixture
def custom_settings() -> RabbitMQSettings:
    return RabbitMQSettings(
        rabbitmq_url="amqp://testuser:testpass@localhost:5672/testvhost",
        rabbitmq_exchange_name="custom_laptop_events",
        rabbitmq_dlx_exchange_name="custom_laptop_events.dlx",
        rabbitmq_prefetch_count=5,
    )


@pytest.mark.asyncio
async def test_rabbitmq_broker_connect_and_declarations(custom_settings):
    broker = RabbitMQBroker(settings=custom_settings)
    assert not broker.is_connected

    mock_connection = AsyncMock()
    mock_connection.is_closed = False
    mock_channel = AsyncMock()
    mock_channel.is_closed = False
    mock_connection.channel.return_value = mock_channel

    with patch("aio_pika.connect_robust", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_connection

        await broker.connect()

        assert broker.is_connected
        mock_connect.assert_called_once_with(
            custom_settings.rabbitmq_url,
            timeout=custom_settings.rabbitmq_connection_timeout_seconds,
        )
        mock_channel.set_qos.assert_called_once_with(prefetch_count=5)

        # Verify DLX and primary exchanges were declared with names from settings
        exchange_declarations = mock_channel.declare_exchange.call_args_list
        declared_names = [call.kwargs.get("name") for call in exchange_declarations]
        assert custom_settings.rabbitmq_dlx_exchange_name in declared_names
        assert custom_settings.rabbitmq_exchange_name in declared_names


@pytest.mark.asyncio
async def test_rabbitmq_broker_publish(custom_settings):
    broker = RabbitMQBroker(settings=custom_settings)

    mock_connection = AsyncMock()
    mock_connection.is_closed = False
    mock_channel = AsyncMock()
    mock_channel.is_closed = False
    mock_exchange = AsyncMock()
    mock_channel.declare_exchange.return_value = mock_exchange
    mock_connection.channel.return_value = mock_channel

    with patch("aio_pika.connect_robust", new_callable=AsyncMock, return_value=mock_connection):
        await broker.connect()

        cmd = ScrapeCatalogCommand(
            payload=ScrapeCatalogPayload(
                batch_id="batch-123",
                targets=["compumarts"],
                level=2,
            )
        )

        await broker.publish(routing_key=EventType.CATALOG_SCRAPE_COMMAND, message=cmd)

        mock_exchange.publish.assert_called_once()
        published_call = mock_exchange.publish.call_args
        msg = published_call[0][0]
        routing_key = published_call[1]["routing_key"]

        assert routing_key == EventType.CATALOG_SCRAPE_COMMAND
        assert b"batch-123" in msg.body
        assert msg.content_type == "application/json"


@pytest.mark.asyncio
async def test_rabbitmq_broker_publish_dict(custom_settings):
    broker = RabbitMQBroker(settings=custom_settings)

    mock_connection = AsyncMock()
    mock_connection.is_closed = False
    mock_channel = AsyncMock()
    mock_channel.is_closed = False
    mock_exchange = AsyncMock()
    mock_channel.declare_exchange.return_value = mock_exchange
    mock_connection.channel.return_value = mock_channel

    with patch("aio_pika.connect_robust", new_callable=AsyncMock, return_value=mock_connection):
        await broker.connect()

        raw_dict = {"event_type": "custom.event", "data": "hello"}
        await broker.publish(routing_key="custom.event", message=raw_dict)

        mock_exchange.publish.assert_called_once()
        published_call = mock_exchange.publish.call_args
        msg = published_call[0][0]
        assert b"hello" in msg.body


@pytest.mark.asyncio
async def test_rabbitmq_broker_subscribe_and_message_processing(custom_settings):
    broker = RabbitMQBroker(settings=custom_settings)

    mock_connection = AsyncMock()
    mock_connection.is_closed = False
    mock_channel = AsyncMock()
    mock_channel.is_closed = False
    mock_exchange = AsyncMock()
    mock_queue = AsyncMock()
    mock_channel.declare_exchange.return_value = mock_exchange
    mock_channel.declare_queue.return_value = mock_queue
    mock_connection.channel.return_value = mock_channel

    handler_received: dict = {}

    async def fake_handler(payload: dict):
        handler_received.update(payload)

    with patch("aio_pika.connect_robust", new_callable=AsyncMock, return_value=mock_connection):
        await broker.connect()

        await broker.subscribe(
            queue_name="catalog.ready.queue",
            routing_key=EventType.CATALOG_READY_EVENT,
            handler=fake_handler,
        )

        # Ensure queue declarations occurred
        assert mock_channel.declare_queue.call_count == 2  # DLQ + main queue
        mock_queue.consume.assert_called_once()

        # Simulate message consumption
        consumer_func = mock_queue.consume.call_args[0][0]

        incoming_msg = MagicMock()
        incoming_msg.body = b'{"batch_id": "b-999", "status": "READY"}'
        incoming_msg.message_id = "msg-123"

        # Mock incoming_msg.process() async context manager
        process_cm = AsyncMock()
        incoming_msg.process.return_value = process_cm
        process_cm.__aenter__.return_value = incoming_msg
        process_cm.__aexit__.return_value = None

        await consumer_func(incoming_msg)

        assert handler_received == {"batch_id": "b-999", "status": "READY"}


@pytest.mark.asyncio
async def test_rabbitmq_broker_close(custom_settings):
    broker = RabbitMQBroker(settings=custom_settings)

    mock_connection = AsyncMock()
    mock_connection.is_closed = False
    mock_channel = AsyncMock()
    mock_channel.is_closed = False
    mock_connection.channel.return_value = mock_channel

    with patch("aio_pika.connect_robust", new_callable=AsyncMock, return_value=mock_connection):
        await broker.connect()
        assert broker.is_connected

        await broker.close()
        assert not broker.is_connected
        mock_channel.close.assert_called_once()
        mock_connection.close.assert_called_once()
