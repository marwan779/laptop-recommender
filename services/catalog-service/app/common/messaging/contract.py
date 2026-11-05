"""Message Broker Interface Contract.

Defines the abstract interface for message broker implementations,
enforcing Dependency Inversion (DIP) and test isolation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel


class IMessageBroker(ABC):
    """Abstract interface defining required capabilities for any message broker."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection, channels, and initialize broker topology."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Gracefully close channels and active broker connections."""
        ...

    @abstractmethod
    async def publish(
        self,
        routing_key: str,
        message: BaseModel | dict[str, Any],
        exchange_name: str | None = None,
    ) -> None:
        """Serialize and publish a message with delivery confirmation.

        Args:
            routing_key: Routing key / topic classifier.
            message: Pydantic model or dictionary payload.
            exchange_name: Target exchange name (uses configured default if omitted).
        """
        ...

    @abstractmethod
    async def subscribe(
        self,
        queue_name: str,
        routing_key: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        exchange_name: str | None = None,
        prefetch_count: int | None = None,
    ) -> None:
        """Declare a queue, bind to an exchange, and consume messages safely.

        The concrete broker is responsible for managing message acknowledgment (ACK)
        upon successful handler completion, or dead-letter rejection on failure.

        Args:
            queue_name: Target queue name.
            routing_key: Topic routing pattern (e.g. 'catalog.ready.event').
            handler: Asynchronous callable processing the incoming message payload.
            exchange_name: Source exchange name (uses configured default if omitted).
            prefetch_count: Optional concurrency limit for this consumer.
        """
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the broker connection is established and healthy."""
        ...
