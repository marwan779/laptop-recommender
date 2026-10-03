"""Tests for FastAPI scraping trigger endpoints (SOLID principles & non-blocking execution)."""

from unittest.mock import MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient
import pytest

from app.api.deps import get_orchestrator
from app.api.routes.scrape import _execute_scrape_background
from app.main import app
from app.schemas.laptop import BrandCatalogResult, StoreCatalogResult
from app.schemas.orchestrator import ScrapeRequest, ScrapeResponse, ScrapeTargetResult
from app.services.orchestrator import ScrapeOrchestrator


@pytest.fixture
def client():
    """TestClient fixture with mock orchestrator dependency override."""
    mock_orchestrator = MagicMock(spec=ScrapeOrchestrator)
    # Default mock response for orchestrator.execute
    mock_orchestrator.execute.return_value = ScrapeResponse(
        results=[],
        total_targets=0,
        total_items_scraped=0,
    )

    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. Health & Root Endpoints
# ---------------------------------------------------------------------------


def test_health_check(client):
    """Verify health endpoint returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "scraper-service"


def test_root_endpoint(client):
    """Verify root endpoint returns service info."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["docs"] == "/docs"


# ---------------------------------------------------------------------------
# 2. Trigger Scrape Endpoints (Non-blocking HTTP 202 Accepted)
# ---------------------------------------------------------------------------


def test_trigger_scrape_brand_all_returns_202_immediately(client):
    """Verify POST /api/v1/scrape returns 202 Accepted immediately with DTO matching."""
    payload = {
        "target_type": "brand",
        "targets": "all",
        "level": 1,
        "send_email": True,
    }

    response = client.post("/api/v1/scrape", json=payload)
    assert response.status_code == status.HTTP_202_ACCEPTED

    data = response.json()
    assert data["status"] == "accepted"
    assert "job_id" in data
    assert "queued_at" in data
    assert data["request"]["target_type"] == "brand"
    assert data["request"]["targets"] == "all"
    assert data["request"]["send_email"] is True


def test_trigger_scrape_store_all_returns_202(client):
    """Verify POST /api/v1/scrape with store targets returns 202."""
    payload = {
        "target_type": "store",
        "targets": "all",
        "level": 2,
        "limit": 10,
    }

    response = client.post("/api/v1/scrape", json=payload)
    assert response.status_code == status.HTTP_202_ACCEPTED

    data = response.json()
    assert data["request"]["target_type"] == "store"
    assert data["request"]["level"] == 2
    assert data["request"]["limit"] == 10
    # send_email must default to True for endpoint triggers
    assert data["request"]["send_email"] is True


def test_trigger_scrape_both_returns_202(client):
    """Verify POST /api/v1/scrape supports 'both' for brands and stores."""
    payload = {
        "target_type": "both",
        "targets": "all",
        "level": 1,
        "send_email": True,
    }

    response = client.post("/api/v1/scrape", json=payload)
    assert response.status_code == status.HTTP_202_ACCEPTED

    data = response.json()
    assert data["request"]["target_type"] == "both"
    assert data["request"]["targets"] == "all"
    assert data["request"]["send_email"] is True


def test_trigger_scrape_specific_targets(client):
    """Verify POST /scrape with a specific list of targets."""
    payload = {
        "target_type": "brand",
        "targets": ["asus", "lenovo"],
        "level": 1,
        "until_model": "S5452",
    }

    response = client.post("/scrape", json=payload)
    assert response.status_code == status.HTTP_202_ACCEPTED

    data = response.json()
    assert data["request"]["targets"] == ["asus", "lenovo"]
    assert data["request"]["until_model"] == "S5452"


def test_trigger_scrape_invalid_target_type(client):
    """Verify 422 Unprocessable Entity when an invalid target_type is provided."""
    payload = {
        "target_type": "unsupported_type",
        "targets": "all",
    }

    response = client.post("/api/v1/scrape", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# 3. Orchestrator 'both' execution tests
# ---------------------------------------------------------------------------


def test_orchestrator_both_resolves_and_executes_brands_and_stores():
    """Verify orchestrator runs both brands and stores when target_type is 'both'."""
    mock_email = MagicMock()
    orchestrator = ScrapeOrchestrator(email_service=mock_email)

    brand_result = ScrapeTargetResult(
        target_type="brand",
        target_key="asus",
        target_name="ASUS",
        level=1,
        items_scraped=10,
    )
    store_result = ScrapeTargetResult(
        target_type="store",
        target_key="compumarts",
        target_name="Compumarts",
        level=1,
        items_scraped=20,
    )

    with (
        patch.object(orchestrator, "_scrape_brand", return_value=brand_result) as mock_brand,
        patch.object(orchestrator, "_scrape_store", return_value=store_result) as mock_store,
    ):
        request = ScrapeRequest(
            target_type="both",
            targets=["asus", "compumarts"],
            level=1,
            send_email=False,
        )

        response = orchestrator.execute(request)

        mock_brand.assert_called_once_with("asus", request)
        mock_store.assert_called_once_with("compumarts", request)
        assert len(response.results) == 2
        assert response.total_items_scraped == 30


def test_version_endpoint(client):
    """Verify /version endpoint returns service name and current version."""
    response = client.get("/version")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["service"] == "scraper-service"
    assert "version" in data


def test_readiness_endpoint(client):
    """Verify /ready endpoint returns ready status."""
    response = client.get("/ready")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["service"] == "scraper-service"
    assert data["ready"] is True


def test_orchestrator_resolve_targets_all_brands():
    """Verify orchestrator expands 'all' brands properly."""
    orchestrator = ScrapeOrchestrator(email_service=MagicMock())
    request = ScrapeRequest(target_type="brand", targets="all", level=1)
    targets = orchestrator._resolve_targets(request)
    assert len(targets) == 4
    assert ("brand", "asus") in targets
    assert ("brand", "lenovo") in targets


def test_orchestrator_resolve_targets_both_mixed():
    """Verify orchestrator resolves mixed brand and store targets."""
    orchestrator = ScrapeOrchestrator(email_service=MagicMock())
    request = ScrapeRequest(target_type="both", targets=["asus", "btech", "unknown_brand"], level=1)
    targets = orchestrator._resolve_targets(request)
    assert ("brand", "asus") in targets
    assert ("store", "btech") in targets
    assert ("brand", "unknown_brand") in targets


def test_orchestrator_scrape_unknown_brand_returns_error():
    """Verify orchestrator gracefully records error for non-existent brand."""
    orchestrator = ScrapeOrchestrator(email_service=MagicMock())
    request = ScrapeRequest(target_type="brand", targets=["nonexistent_brand"], level=1)
    result = orchestrator._scrape_brand("nonexistent_brand", request)
    assert result.error is not None
    assert "Unknown brand" in result.error
    assert result.items_scraped == 0


def test_execute_scrape_background_success():
    """Verify background scrape worker executes orchestrator successfully."""
    mock_orchestrator = MagicMock(spec=ScrapeOrchestrator)
    mock_orchestrator.execute.return_value = ScrapeResponse(
        results=[],
        total_targets=1,
        total_items_scraped=5,
    )
    request = ScrapeRequest(target_type="brand", targets=["asus"], level=1)

    _execute_scrape_background(mock_orchestrator, request, "job-test-123")

    mock_orchestrator.execute.assert_called_once_with(request)


def test_execute_scrape_background_handles_exception():
    """Verify background scrape worker catches exceptions gracefully without raising."""
    mock_orchestrator = MagicMock(spec=ScrapeOrchestrator)
    mock_orchestrator.execute.side_effect = RuntimeError("Worker failure test")
    request = ScrapeRequest(target_type="store", targets=["btech"], level=1)

    # Should not raise exception
    _execute_scrape_background(mock_orchestrator, request, "job-fail-123")
    mock_orchestrator.execute.assert_called_once_with(request)
