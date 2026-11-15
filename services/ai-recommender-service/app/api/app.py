"""FastAPI application factory / lifespan wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import _get_service, router


@asynccontextmanager
async def lifespan(app: FastAPI):
    _get_service()
    yield


app = FastAPI(
    title="Egyptian Laptop Recommender & Workload AI Microservice",
    version="1.0.0",
    description="10-column Vector TOPSIS + Jina-v3 (512d) Dual-Vector ChromaDB + Deterministic Workloads API.",
    lifespan=lifespan,
)
app.include_router(router)
