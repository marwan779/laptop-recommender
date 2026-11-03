from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.core.database import get_db
from app.main import app


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "catalog-service"
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_endpoint_healthy(async_client: AsyncClient):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_session.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_health_endpoint_db_failure(async_client: AsyncClient):
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("connection refused")

    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "unhealthy" in data["database"]
    finally:
        app.dependency_overrides.pop(get_db, None)
