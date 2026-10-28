from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.core.config import settings
from app.core.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Engine connection pool is ready
    yield
    # Shutdown: Cleanly dispose connection pool
    await engine.dispose()


app = FastAPI(
    title="Laptop Catalog & Recommendation Service",
    description="Authoritative product catalog, hardware scoring engine, and recommendation API.",
    version="0.2.0",
    lifespan=lifespan,
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
