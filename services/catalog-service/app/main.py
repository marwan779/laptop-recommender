from fastapi import FastAPI
from app.api.routes.health import router as health_router

app = FastAPI(
    title="Laptop Catalog Service",
    description="Catalog and Phase 1 recommendation service for the laptop recommendation platform.",
    version="0.1.0",
)

app.include_router(health_router)
@app.get("/")
def root():
    return {
        "service": "catalog-service",
        "status": "ok",
    }


