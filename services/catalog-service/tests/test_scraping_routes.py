import uuid
from datetime import datetime, timezone, UTC
import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.models.scraping import StoreScrapingPointer
from app.schemas.scraping import ScrapeTriggerRequest
from app.services.scraper_client import ScraperClientService


@pytest.mark.asyncio
async def test_get_store_pointers_route(db_session: AsyncSession):
    pointer = StoreScrapingPointer(
        store_key="compumarts",
        store_name="Compumarts",
        store_domain="compumarts.com",
        latest_pointers=["Lenovo Legion Pro 5", "Asus TUF A15"],
        total_active_offers=150,
        scrape_interval_hours=24,
        is_active=True,
    )
    await db_session.merge(pointer)
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/scraping/pointers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        compumarts_p = next(p for p in data if p["store_key"] == "compumarts")
        assert compumarts_p["store_name"] == "Compumarts"
        assert compumarts_p["latest_pointers"] == ["Lenovo Legion Pro 5", "Asus TUF A15"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_trigger_scrape_with_pointers_mock_dispatch(db_session: AsyncSession):
    pointer = StoreScrapingPointer(
        store_key="sigma",
        store_name="Sigma Computer",
        store_domain="sigma-computer.com",
        latest_pointers=["Dell Alienware m16"],
        total_active_offers=80,
        is_active=True,
    )
    await db_session.merge(pointer)
    await db_session.commit()

    service = ScraperClientService()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        assert body["targets"] == ["sigma"]
        assert body["until_model"] == ["Dell Alienware m16"]
        return httpx.Response(202, json={"status": "accepted", "job_id": str(uuid.uuid4())})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    req = ScrapeTriggerRequest(store_key="sigma", level=2, force_full_crawl=False)
    result = await service.trigger_scrape_job(session=db_session, request=req, client=mock_client)

    assert result.status == "DISPATCHED"
    assert "sigma" in result.stores_targeted
    assert result.pointers_used["sigma"] == ["Dell Alienware m16"]


@pytest.mark.asyncio
async def test_trigger_scrape_force_full_crawl_omits_pointers(db_session: AsyncSession):
    pointer = StoreScrapingPointer(
        store_key="elbadr",
        store_name="El Badr Group",
        store_domain="elbadrgroupeg.store",
        latest_pointers=["Acer Predator Helios 16"],
        total_active_offers=60,
        is_active=True,
    )
    await db_session.merge(pointer)
    await db_session.commit()

    service = ScraperClientService()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        assert body["targets"] == ["elbadr"]
        assert body["until_model"] is None
        return httpx.Response(202, json={"status": "accepted"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    req = ScrapeTriggerRequest(store_key="elbadr", level=2, force_full_crawl=True)
    result = await service.trigger_scrape_job(session=db_session, request=req, client=mock_client)

    assert result.status == "DISPATCHED"
    assert result.pointers_used == {}


@pytest.mark.asyncio
async def test_get_scraping_logs_route(db_session: AsyncSession):
    from app.models.scraping import ScrapingBatchLog

    log_entry = ScrapingBatchLog(
        id=uuid.uuid4(),
        store_key="compumarts",
        trigger_type="CRON",
        status="SUCCESS",
        started_at=datetime.now(UTC),
        items_scraped=42,
        new_laptops_added=5,
        offers_updated=12,
    )
    db_session.add(log_entry)
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/scraping/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any(d["store_key"] == "compumarts" for d in data)

    app.dependency_overrides.clear()
