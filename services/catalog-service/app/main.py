from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import setup_exception_handlers
from app.api.middleware import CorrelationIdMiddleware
from app.api.routes.health import router as health_router
from app.common.logger import configure_logging, get_logger
from app.core.config import settings
from app.core.database import engine

# Initialize unified logging subsystem
configure_logging()
logger = get_logger("catalog.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s in %s mode", settings.service_name, settings.environment)
    yield
    logger.info("Shutting down %s: closing database connection pool", settings.service_name)
    await engine.dispose()


app = FastAPI(
    title="Laptop Catalog & Recommendation Service",
    description="Authoritative product catalog, hardware scoring engine, and recommendation API.",
    version="0.2.0",
    lifespan=lifespan,
)

# Exception handlers
setup_exception_handlers(app)

# Middlewares
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health_router)


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": settings.service_name,
        "environment": settings.environment,
        "status": "ok",
    }
