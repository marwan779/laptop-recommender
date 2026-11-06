from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import setup_exception_handlers
from app.api.middleware import CorrelationIdMiddleware, ResponseCacheMiddleware
from app.api.routes.catalog import router as catalog_router
from app.api.routes.health import router as health_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.scraping import router as scraping_router
from app.common.cache import InMemoryCacheProvider, RedisCacheProvider
from app.common.logger import configure_logging, get_logger
from app.common.messaging.rabbitmq import RabbitMQBroker
from app.core.config import settings
from app.core.database import engine
from app.jobs import outbox_relay, price_sync_cron, scraping_cron
from app.services.messaging_consumer import CatalogMessageConsumer

# Initialize unified logging subsystem
configure_logging()
logger = get_logger("catalog.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting %s in %s mode", settings.service_name, settings.environment)

    # 1. Initialize Cache Provider (Redis with graceful fallback to In-Memory)
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

    # 2. Initialize RabbitMQ broker & consumer
    broker = RabbitMQBroker()
    consumer = CatalogMessageConsumer(broker=broker)
    app.state.broker = broker
    app.state.consumer = consumer

    # Wire broker into outbox_relay singleton
    outbox_relay.broker = broker

    try:
        await broker.connect()
        await consumer.start_listening()
        logger.info("RabbitMQ broker connected and consumers successfully listening.")
    except Exception as exc:
        logger.warning(
            "RabbitMQ broker could not connect on startup (%s). Operating in degraded mode.",
            exc,
        )

    # 3. Start background workers
    outbox_relay.start()
    scraping_cron.start()
    price_sync_cron.start()

    yield

    logger.info("Shutting down %s: closing background jobs, cache, broker, and database pool", settings.service_name)
    await price_sync_cron.stop()
    await scraping_cron.stop()
    await outbox_relay.stop()

    if getattr(app.state, "cache", None):
        try:
            await app.state.cache.close()
        except Exception as exc:
            logger.warning("Error during cache provider shutdown: %s", exc)

    if getattr(app.state, "broker", None) and app.state.broker.is_connected:
        try:
            await app.state.broker.close()
        except Exception as exc:
            logger.warning("Error during RabbitMQ shutdown: %s", exc)

    await engine.dispose()


app = FastAPI(
    title="Laptop Catalog & Recommendation Service",
    description="Authoritative product catalog, hardware scoring engine, and recommendation API.",
    version="0.2.0",
    lifespan=lifespan,
)

# Exception handlers
setup_exception_handlers(app)

# Middlewares (LIFO execution: CorrelationId -> ResponseCache -> Route)
app.add_middleware(ResponseCacheMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Cache", "X-Cache-Key", "X-Cache-Lookup-Time-Ms", "X-Correlation-ID"],
)

# Register routes
app.include_router(health_router)
app.include_router(scraping_router, prefix=settings.api_prefix)
app.include_router(recommendations_router, prefix=settings.api_prefix)
app.include_router(catalog_router, prefix=settings.api_prefix)


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": settings.service_name,
        "environment": settings.environment,
        "status": "ok",
    }
