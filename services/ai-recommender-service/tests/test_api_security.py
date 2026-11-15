"""Tests for X-API-Key authentication on the ai-recommender HTTP API."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes as routes_module
from app.api.app import app
from app.api.middlewares import APIKeyAuthMiddleware
from app.core.security_config import SecuritySettings, get_security_settings


class _FakeCacheInfo:
    hits = 0
    misses = 0
    maxsize = 128
    currsize = 0


class _FakeDualQuery:
    def cache_info(self) -> _FakeCacheInfo:
        return _FakeCacheInfo()


class _FakeCollection:
    def count(self) -> int:
        return 0


class _FakeService:
    """Minimal stand-in for LaptopRecommenderService used by HTTP routes."""

    def __init__(self) -> None:
        self.query_emb_fn = object()
        self.collection = _FakeCollection()
        self._cached_catalog: list[dict[str, Any]] = []
        self._cached_dual_query = _FakeDualQuery()

    def recommend(self, **kwargs: Any) -> dict[str, Any]:
        return {"status": "OK", "results": [], "kwargs": sorted(kwargs)}


@pytest.fixture
def fake_service(monkeypatch: pytest.MonkeyPatch) -> _FakeService:
    service = _FakeService()
    monkeypatch.setattr(routes_module, "_get_service", lambda: service)
    return service


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _use_security(settings: SecuritySettings) -> None:
    app.dependency_overrides[get_security_settings] = lambda: settings


@pytest.fixture(autouse=True)
def _clear_overrides():
    get_security_settings.cache_clear()
    yield
    app.dependency_overrides.clear()
    get_security_settings.cache_clear()


def test_health_endpoint_stays_public_with_api_key_configured(
    client: TestClient, fake_service: _FakeService
) -> None:
    _use_security(SecuritySettings(ai_recommender_api_key="secret", require_api_key=True))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/recommend", "/ingest-reviews"])
@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong-key"}])
def test_protected_routes_reject_missing_or_wrong_key(
    client: TestClient,
    fake_service: _FakeService,
    path: str,
    headers: dict[str, str],
) -> None:
    _use_security(SecuritySettings(ai_recommender_api_key="secret", require_api_key=True))

    response = client.post(path, json={}, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing X-API-Key"
    assert response.headers["www-authenticate"] == "ApiKey"


def test_protected_route_returns_503_when_server_key_missing(
    client: TestClient, fake_service: _FakeService
) -> None:
    _use_security(SecuritySettings(ai_recommender_api_key="", require_api_key=True))

    response = client.post("/recommend", json={}, headers={"X-API-Key": ""})

    assert response.status_code == 503
    assert response.json()["detail"] == "API key authentication is not configured"


def test_protected_route_accepts_matching_key(
    client: TestClient, fake_service: _FakeService
) -> None:
    _use_security(SecuritySettings(ai_recommender_api_key="secret", require_api_key=True))

    response = client.post("/recommend", json={}, headers={"X-API-Key": "secret"})

    assert response.status_code == 200
    assert response.json()["status"] == "OK"


def test_protected_route_allows_requests_when_auth_disabled(
    client: TestClient, fake_service: _FakeService
) -> None:
    _use_security(SecuritySettings(ai_recommender_api_key="", require_api_key=False))

    response = client.post("/recommend", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "OK"


def test_security_settings_strip_whitespace_only_strings() -> None:
    settings = SecuritySettings(ai_recommender_api_key="   ", require_api_key=True)

    assert settings.ai_recommender_api_key == ""
    assert settings.api_key_configured is False

    configured = SecuritySettings(ai_recommender_api_key="  secret  ")
    assert configured.api_key_configured is True


def test_middleware_protects_all_non_public_paths_by_default(
    client: TestClient, fake_service: _FakeService
) -> None:
    _use_security(SecuritySettings(ai_recommender_api_key="secret", require_api_key=True))

    # Blocked before routing (401 rather than 404) when X-API-Key is absent
    unauth = client.get("/any-future-route")
    assert unauth.status_code == 401

    # Proceeds to normal routing (404) once authenticated
    auth = client.get("/any-future-route", headers={"X-API-Key": "secret"})
    assert auth.status_code == 404


def test_standalone_generic_middleware_protects_routes_without_per_route_depends() -> None:
    mini_app = FastAPI()
    mini_app.add_middleware(
        APIKeyAuthMiddleware,
        settings_provider=lambda: SecuritySettings(
            ai_recommender_api_key="top-secret",
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
    assert mini_client.get("/custom", headers={"X-API-Key": "top-secret"}).json() == {"ok": "yes"}
