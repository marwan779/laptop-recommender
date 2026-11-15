"""Tests for X-API-Key authentication on the scraper-service HTTP API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_orchestrator
from app.api.middlewares import APIKeyAuthMiddleware
from app.core.security_config import SecuritySettings, get_security_settings
from app.main import app
from app.price_monitor.models import PriceCheckBatchResponse
from app.schemas.orchestrator import ScrapeResponse
from app.services.orchestrator import ScrapeOrchestrator

PROTECTED_ROUTES = [
    ("/scrape", "POST"),
    ("/api/v1/scrape", "POST"),
    ("/price-monitor/check", "POST"),
    ("/api/v1/price-monitor/check", "POST"),
    ("/", "GET"),
    ("/version", "GET"),
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _use_security(settings: SecuritySettings) -> None:
    app.dependency_overrides[get_security_settings] = lambda: settings


def _use_fake_orchestrator() -> None:
    orchestrator = MagicMock(spec=ScrapeOrchestrator)
    orchestrator.execute.return_value = ScrapeResponse(
        results=[],
        total_targets=0,
        total_items_scraped=0,
    )
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator


@pytest.fixture(autouse=True)
def _clear_overrides():
    get_security_settings.cache_clear()
    yield
    app.dependency_overrides.clear()
    get_security_settings.cache_clear()


def test_health_and_ready_stay_public_with_api_key_configured(
    client: TestClient,
) -> None:
    _use_security(SecuritySettings(scraper_api_key="secret", require_api_key=True))

    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["ready"] is True


@pytest.mark.parametrize(("path", "method"), PROTECTED_ROUTES)
@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong-key"}])
def test_protected_routes_reject_missing_or_wrong_key(
    client: TestClient,
    path: str,
    method: str,
    headers: dict[str, str],
) -> None:
    _use_security(SecuritySettings(scraper_api_key="secret", require_api_key=True))

    response = client.request(method, path, json={}, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing X-API-Key"
    assert response.headers["www-authenticate"] == "ApiKey"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_openapi_docs_routes_require_api_key(
    client: TestClient, path: str
) -> None:
    _use_security(SecuritySettings(scraper_api_key="secret", require_api_key=True))

    response = client.get(path)

    assert response.status_code == 401


def test_protected_route_returns_503_when_server_key_missing(
    client: TestClient,
) -> None:
    _use_security(SecuritySettings(scraper_api_key="", require_api_key=True))

    response = client.post("/api/v1/scrape", json={}, headers={"X-API-Key": ""})

    assert response.status_code == 503
    assert response.json()["detail"] == "API key authentication is not configured"


@pytest.mark.parametrize("configured_key", ["secret", "  secret  "])
def test_protected_route_accepts_matching_key(
    client: TestClient,
    configured_key: str,
) -> None:
    _use_security(
        SecuritySettings(scraper_api_key=configured_key, require_api_key=True)
    )
    _use_fake_orchestrator()

    response = client.post(
        "/api/v1/scrape",
        json={"target_type": "brand", "targets": ["asus"], "level": 1},
        headers={"X-API-Key": "secret"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"


def test_price_monitor_accepts_matching_key(client: TestClient) -> None:
    _use_security(SecuritySettings(scraper_api_key="secret", require_api_key=True))
    mock_response = PriceCheckBatchResponse(
        batch_id="batch-1",
        store_key="compumarts",
        total_items=0,
        changed_items_count=0,
        price_drops_count=0,
        results=[],
    )

    with patch(
        "app.price_monitor.service.PriceMonitorService.check_batch_async",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        response = client.post(
            "/price-monitor/check",
            json={
                "batch_id": "batch-1",
                "store_key": "compumarts",
                "store_name": "Compumarts",
                "items": [],
            },
            headers={"X-API-Key": "secret"},
        )

    assert response.status_code == 200
    assert response.json()["batch_id"] == "batch-1"


def test_protected_route_allows_requests_when_auth_disabled(
    client: TestClient,
) -> None:
    _use_security(SecuritySettings(scraper_api_key="", require_api_key=False))

    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["service"] == "scraper-service"


def test_security_settings_strip_whitespace_only_strings() -> None:
    settings = SecuritySettings(scraper_api_key="   ", require_api_key=True)

    assert settings.scraper_api_key == ""
    assert settings.api_key_configured is False

    configured = SecuritySettings(scraper_api_key="  secret  ")
    assert configured.api_key_configured is True


def test_middleware_protects_all_non_public_paths_by_default(
    client: TestClient,
) -> None:
    _use_security(SecuritySettings(scraper_api_key="secret", require_api_key=True))

    # Blocked before routing (401 rather than 404) when X-API-Key is absent
    unauth = client.get("/any-future-route")
    assert unauth.status_code == 401

    # Proceeds to normal routing (404) once authenticated
    auth = client.get("/any-future-route", headers={"X-API-Key": "secret"})
    assert auth.status_code == 404


def test_options_preflight_is_not_blocked_by_api_key_middleware() -> None:
    mini_app = FastAPI()
    mini_app.add_middleware(
        APIKeyAuthMiddleware,
        settings_provider=lambda: SecuritySettings(
            scraper_api_key="top-secret",
            require_api_key=True,
        ),
    )

    @mini_app.get("/custom")
    def _custom() -> dict[str, str]:
        return {"ok": "yes"}

    mini_client = TestClient(mini_app)
    response = mini_client.options("/custom")

    assert response.status_code != 401


def test_standalone_generic_middleware_protects_routes_without_per_route_depends() -> None:
    mini_app = FastAPI()
    mini_app.add_middleware(
        APIKeyAuthMiddleware,
        settings_provider=lambda: SecuritySettings(
            scraper_api_key="top-secret",
            require_api_key=True,
        ),
    )

    @mini_app.get("/health")
    def _health() -> dict[str, str]:
        return {"status": "ok"}

    @mini_app.get("/custom")
    def _custom() -> dict[str, str]:
        return {"ok": "yes"}

    mini_client = TestClient(mini_app)
    assert mini_client.get("/health").status_code == 200
    assert mini_client.get("/health/").status_code == 200
    assert mini_client.get("/custom").status_code == 401
    assert mini_client.get("/custom", headers={"X-API-Key": "top-secret"}).json() == {
        "ok": "yes"
    }
