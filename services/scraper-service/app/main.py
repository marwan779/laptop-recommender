"""FastAPI Application entry-point for Scraper Service."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.price_monitor import router as price_monitor_router
from app.api.routes.scrape import router as scrape_router
from app.common.logger import configure_logging, get_logger
from app.common.messaging.rabbitmq import RabbitMQBroker
from app.services.messaging_consumer import ScraperMessageConsumer

configure_logging()
logger = get_logger("scraper.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycles."""
    logger.info("Initializing RabbitMQ event broker and command consumers...")
    broker = RabbitMQBroker()
    consumer = ScraperMessageConsumer(broker=broker)
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

# Allow cross-origin requests from downstream services and dashboards
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
