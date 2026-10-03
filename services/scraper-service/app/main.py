"""FastAPI Application entry-point for Scraper Service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.scrape import router as scrape_router

app = FastAPI(
    title="Laptop Scraper Service",
    description="Autonomous web scraper service for official laptop brand portals and Egyptian retail stores.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
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


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for container orchestrators and load balancers."""
    return {
        "service": "scraper-service",
        "status": "ok",
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


@app.get("/live", tags=["Health"])
def liveness_check():
    """Liveness probe endpoint for container orchestrators."""
    return {
        "service": "scraper-service",
        "alive": True,
    }
