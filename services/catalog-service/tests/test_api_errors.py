import pytest
from httpx import AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_correlation_id_injected_in_headers(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers
    assert len(response.headers["X-Correlation-ID"]) > 10


@pytest.mark.asyncio
async def test_custom_correlation_id_propagated(async_client: AsyncClient):
    custom_cid = "custom-test-cid-999"
    response = await async_client.get("/", headers={"X-Correlation-ID": custom_cid})
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == custom_cid


@pytest.mark.asyncio
async def test_404_error_handler_structure(async_client: AsyncClient):
    response = await async_client.get("/non-existent-path")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == 404
    assert "correlation_id" in data["error"]
