"""Security-focused tests for the catalog-service HTTP scraper client."""

from __future__ import annotations

import logging
import uuid

import httpx
import pytest

from app.models.scraping import ScrapingBatchLog
from app.schemas.scraping import ScrapeTriggerRequest
from app.services.scraper_client import ScraperClientService


class _FakeSession:
    """Minimal AsyncSession stand-in capturing persisted objects."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def _without_pointers(service: ScraperClientService) -> ScraperClientService:
    async def _no_pointers(session, store_key=None):  # type: ignore[no-untyped-def]
        return []

    service.get_active_store_pointers = _no_pointers  # type: ignore[method-assign]
    return service


def _batch_log(session: _FakeSession) -> ScrapingBatchLog:
    logs = [item for item in session.added if isinstance(item, ScrapingBatchLog)]
    assert len(logs) == 1
    return logs[0]


@pytest.mark.asyncio
async def test_scraper_client_sends_api_key_header_when_configured() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.headers)
        return httpx.Response(202, json={"status": "accepted", "job_id": str(uuid.uuid4())})

    service = _without_pointers(
        ScraperClientService(
            scraper_url="http://scraper-service:8001",
            api_key="secret-inter-service-key",
        )
    )
    session = _FakeSession()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await service.trigger_scrape_job(
            session=session,  # type: ignore[arg-type]
            request=ScrapeTriggerRequest(store_key="sigma"),
            client=client,
        )

    assert result.status == "DISPATCHED"
    assert captured["x-api-key"] == "secret-inter-service-key"


@pytest.mark.asyncio
async def test_scraper_client_omits_api_key_header_when_empty() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.headers)
        return httpx.Response(202, json={"status": "accepted"})

    service = _without_pointers(
        ScraperClientService(scraper_url="http://scraper-service:8001", api_key="")
    )
    session = _FakeSession()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await service.trigger_scrape_job(
            session=session,  # type: ignore[arg-type]
            request=ScrapeTriggerRequest(store_key="sigma"),
            client=client,
        )

    assert result.status == "DISPATCHED"
    assert "x-api-key" not in captured


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 503])
async def test_scraper_client_handles_auth_failures_without_leaking_key(
    status_code: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "super-secret-scraper-key"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": "Invalid or missing X-API-Key"})

    service = _without_pointers(
        ScraperClientService(
            scraper_url="http://scraper-service:8001",
            api_key=secret,
        )
    )
    session = _FakeSession()

    with caplog.at_level(logging.WARNING, logger="app.services.scraper_client"):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await service.trigger_scrape_job(
                session=session,  # type: ignore[arg-type]
                request=ScrapeTriggerRequest(store_key="sigma"),
                client=client,
            )

    batch_log = _batch_log(session)
    assert result.status == "DISPATCH_FAILED"
    assert batch_log.status == "DISPATCH_FAILED"
    assert str(status_code) in caplog.text
    assert "SCRAPER_API_KEY" in caplog.text
    assert secret not in caplog.text
    assert batch_log.error_message is not None
    assert secret not in batch_log.error_message
    assert "SCRAPER_API_KEY" in batch_log.error_message
