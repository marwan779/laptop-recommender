import json
import uuid
from datetime import datetime, timezone, UTC
import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.main import app
from app.models.laptop import LaptopConfiguration
from app.models.outbox import OutboxMessage
from app.models.scraping import StoreScrapingPointer
from app.schemas.events import EventType
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


@pytest.mark.asyncio
async def test_trigger_reviews_scraping_queues_outbox_command(db_session: AsyncSession):
    """Stage 2 trigger resolves chassis targets and writes a reviews.scrape.command outbox event."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/scraping/reviews/trigger",
            json={"force_all": True},
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "QUEUED"
    assert data["chassis_targets_queued"] >= 1
    assert data["laptops_matched"] >= data["chassis_targets_queued"]

    stmt = select(OutboxMessage).where(OutboxMessage.correlation_id == data["job_id"])
    message = (await db_session.execute(stmt)).scalar_one()
    assert message.event_type == EventType.REVIEWS_SCRAPE_COMMAND
    assert message.routing_key == EventType.REVIEWS_SCRAPE_COMMAND


@pytest.mark.asyncio
async def test_ingest_reviews_updates_chroma_and_postgres(
    db_session: AsyncSession,
    tmp_path,
):
    """Stage 2 ingest embeds chassis reviews and persists the SQL NLP profile."""
    canonical_id = "laptop_msi_prestige_9s713q222261"
    reviews_payload = {
        "laptops": [
            {
                "chassis_key": "msi:prestige:9s7-13q222-261",
                "primary_canonical_id": canonical_id,
                "matched_canonical_ids": [canonical_id],
                "nlp_review_profile": {
                    "community_nlp_score": 81.5,
                    "evidence_count": 11,
                    "aspect_scores": {
                        "thermals_score": 77.0,
                        "acoustics_score": 73.5,
                        "build_and_hinges_score": 84.0,
                        "keyboard_and_trackpad_score": 82.5,
                        "real_battery_and_reliability_score": 79.0,
                    },
                    "pros_ar": ["بناء قوي ومفصلات متينة"],
                    "pros_en": ["Solid build and strong hinges"],
                    "cons_ar": ["صوت المراوح مرتفع تحت الحمل"],
                    "cons_en": ["Fan noise under sustained load"],
                },
            }
        ]
    }
    reviews_file = tmp_path / "enriched_reviews.json"
    reviews_file.write_text(json.dumps(reviews_payload, ensure_ascii=False), encoding="utf-8")

    class _FakeChroma:
        def __init__(self) -> None:
            self.upserted: list[dict] = []

        def upsert_chassis_reviews(self, laptops):
            self.upserted = list(laptops)
            return 3

    fake_chroma = _FakeChroma()
    original_chroma = getattr(app.state, "chroma_reviews", None)
    app.state.chroma_reviews = fake_chroma

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/scraping/reviews/ingest",
                json={"source_path": str(reviews_file), "from_s3": False},
            )
    finally:
        app.dependency_overrides.clear()
        app.state.chroma_reviews = original_chroma

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["chassis_processed"] == 1
    assert data["chroma_documents_upserted"] == 3
    assert data["sql_laptops_updated"] == 1
    assert len(fake_chroma.upserted) == 1

    stmt = (
        select(LaptopConfiguration)
        .where(LaptopConfiguration.canonical_id == canonical_id)
        .options(selectinload(LaptopConfiguration.metrics))
    )
    laptop = (await db_session.execute(stmt)).scalar_one()

    assert laptop.has_reviews is True
    assert laptop.reviews_evidence_count == 11
    assert laptop.pros_en == ["Solid build and strong hinges"]
    assert laptop.pros_ar == ["بناء قوي ومفصلات متينة"]
    assert laptop.cons_en == ["Fan noise under sustained load"]
    assert laptop.cons_ar == ["صوت المراوح مرتفع تحت الحمل"]
    assert laptop.metrics is not None
    assert float(laptop.metrics.community_nlp_score) == 81.5
    assert float(laptop.metrics.thermals_score) == 77.0
    assert float(laptop.metrics.real_battery_and_reliability_score) == 79.0


@pytest.mark.asyncio
async def test_ingest_reviews_missing_file_returns_404(db_session: AsyncSession, tmp_path):
    """A missing local reviews artifact returns 404 instead of a server error."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/scraping/reviews/ingest",
            json={
                "source_path": str(tmp_path / "does_not_exist.json"),
                "from_s3": False,
            },
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 404
