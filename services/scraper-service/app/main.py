"""FastAPI Application entry-point for Scraper Service."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middlewares import APIKeyAuthMiddleware
from app.api.routes.price_monitor import router as price_monitor_router
from app.api.routes.scrape import router as scrape_router
from app.common.cache import InMemoryCacheProvider, RedisCacheProvider
from app.common.logger import configure_logging, get_logger
from app.common.messaging.inbox import RedisInboxDeduplicator
from app.common.messaging.rabbitmq import RabbitMQBroker
from app.core.security_config import get_security_settings
from app.services.messaging_consumer import ScraperMessageConsumer

configure_logging()
logger = get_logger("scraper.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycles."""
    # 1. Initialize the distributed cache used for inbox deduplication.
    redis_cache = RedisCacheProvider()
    await redis_cache.connect()
    if await redis_cache.health_check():
        cache = redis_cache
    else:
        await redis_cache.close()
        cache = InMemoryCacheProvider()
        await cache.connect()
        logger.warning(
            "Redis cache is unavailable; falling back to process-local inbox deduplication. "
            "Duplicate protection is not shared across replicas."
        )
    app.state.cache = cache
    app.state.inbox = RedisInboxDeduplicator(cache)

    # Report X-API-Key authentication posture (never log the key value)
    security = get_security_settings()
    if security.require_api_key and not security.api_key_configured:
        logger.warning(
            "SCRAPER_API_KEY is not configured while REQUIRE_API_KEY is true. "
            "Protected routes will return HTTP 503 until it is set in .env."
        )
    elif security.require_api_key:
        logger.info("X-API-Key authentication is enabled for protected routes.")
    else:
        logger.info("X-API-Key authentication is disabled; protected routes are open.")

    logger.info("Initializing RabbitMQ event broker and command consumers...")
    broker = RabbitMQBroker()
    consumer = ScraperMessageConsumer(broker=broker, inbox=app.state.inbox)
    app.state.broker = broker
    app.state.consumer = consumer

    try:
        await broker.connect()
        await consumer.start_listening()
        logger.info("RabbitMQ broker connected and consumers successfully listening.")
    except Exception as exc:
        logger.warning(
            "RabbitMQ could not connect on startup (%s). Service operating in standalone/HTTP mode.",
            exc,
        )

    yield

    # Graceful shutdown
    if getattr(app.state, "cache", None):
        try:
            await app.state.cache.close()
        except Exception as exc:
            logger.warning("Error during cache provider shutdown: %s", exc)

    if getattr(app.state, "broker", None) and app.state.broker.is_connected:
        logger.info("Shutting down RabbitMQ connection...")
        try:
            await app.state.broker.close()
        except Exception as exc:
            logger.warning("Error during RabbitMQ shutdown: %s", exc)


app = FastAPI(
    title="Laptop Scraper Service",
    description="Autonomous web scraper service for official laptop brand portals and Egyptian retail stores.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Middlewares run in LIFO order: the API key guard is registered first so
# CORSMiddleware remains the outermost layer and decorates 401/503 responses too.
app.add_middleware(APIKeyAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route mounts
app.include_router(scrape_router, prefix="/api/v1")
app.include_router(scrape_router)
app.include_router(price_monitor_router, prefix="/api/v1")
app.include_router(price_monitor_router)


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for container orchestrators and load balancers."""
    broker_ok = bool(getattr(app.state, "broker", None) and app.state.broker.is_connected)
    return {
        "service": "scraper-service",
        "status": "ok",
        "rabbitmq_connected": broker_ok,
    }


@app.get("/", tags=["Health"])
def root():
    """Root metadata endpoint."""
    return {
        "service": "scraper-service",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/version", tags=["Health"])
def version():
    """Return the current service version."""
    return {
        "service": "scraper-service",
        "version": app.version,
    }


@app.get("/ready", tags=["Health"])
def readiness_check():
    """Readiness probe endpoint for container orchestrators."""
    return {
        "service": "scraper-service",
        "ready": True,
    }
