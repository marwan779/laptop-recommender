"""FastAPI application factory / lifespan wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import _get_service, router
from app.common.cache import InMemoryCacheProvider, RedisCacheProvider
from app.common.logger import configure_logging, get_logger
from app.common.messaging import RabbitMQBroker, RedisInboxDeduplicator
from app.services.messaging_consumer import AIRecommenderMessageConsumer

configure_logging()
logger = get_logger("ai_recommender.api.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Warm up singleton Jina-v3 / ChromaDB recommendation pipeline
    _get_service()

    # 2. Initialize Cache Provider (Redis with graceful fallback to In-Memory)
    redis_cache = RedisCacheProvider()
    await redis_cache.connect()
    if await redis_cache.health_check():
        app.state.cache = redis_cache
    else:
        await redis_cache.close()
        memory_cache = InMemoryCacheProvider()
        await memory_cache.connect()
        app.state.cache = memory_cache
        logger.info("Using InMemoryCacheProvider fallback while Redis is offline.")

    # 3. Initialize RabbitMQ broker & review enrichment consumer
    inbox = RedisInboxDeduplicator(cache=app.state.cache)
    broker = RabbitMQBroker()
    consumer = AIRecommenderMessageConsumer(broker=broker, inbox=inbox)
    app.state.broker = broker
    app.state.inbox = inbox
    app.state.consumer = consumer

    try:
        await broker.connect()
        await consumer.start_listening()
        logger.info("RabbitMQ broker connected and AIRecommenderMessageConsumer listening.")
    except Exception as exc:
        logger.warning(
            "RabbitMQ broker could not connect on startup (%s). Operating in HTTP-only degraded mode.",
            exc,
        )

    yield

    if getattr(app.state, "broker", None) and app.state.broker.is_connected:
        try:
            await app.state.broker.close()
        except Exception as exc:
            logger.warning("Error during RabbitMQ shutdown: %s", exc)

    if getattr(app.state, "cache", None):
        try:
            await app.state.cache.close()
        except Exception as exc:
            logger.warning("Error during cache shutdown: %s", exc)


app = FastAPI(
    title="Egyptian Laptop Recommender & Workload AI Microservice",
    version="1.0.0",
    description="10-column Vector TOPSIS + Jina-v3 (512d) Dual-Vector ChromaDB + Deterministic Workloads API.",
    lifespan=lifespan,
)
app.include_router(router)
