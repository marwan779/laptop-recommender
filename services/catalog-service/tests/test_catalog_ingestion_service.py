import json
from pathlib import Path
from unittest.mock import MagicMock
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.storage.base import IObjectStorageService
from app.models.laptop import LaptopConfiguration
from app.models.scraping import ScrapingBatchLog, StoreScrapingPointer
from app.services.catalog_ingestion_service import CatalogIngestionService, IngestionResult
from tests.test_catalog_seeder import _build_sample_catalog_item


@pytest.mark.asyncio
async def test_ingest_from_file_full_pipeline(db_session: AsyncSession, tmp_path: Path):
    cid = f"test_ingest_file_{uuid.uuid4().hex[:8]}"
    catalog_dict = {
        "title": "Unified Catalog Test",
        "stores_included": ["compumarts", "elbadr"],
        "laptops": [
            _build_sample_catalog_item(cid, mpn=f"MPN-INGEST-{uuid.uuid4().hex[:6]}", min_price=45000.0),
        ],
    }

    test_file = tmp_path / "unified_catalog_test.json"
    with open(test_file, "w", encoding="utf-8") as f:
        json.dump(catalog_dict, f)

    service = CatalogIngestionService()
    result: IngestionResult = await service.ingest_from_file(
        session=db_session,
        file_path=test_file,
        trigger_type="TEST_FILE_INGESTION",
    )

    assert result.status == "SUCCESS"
    assert result.total_laptops == 1
    assert result.new_laptops == 1
    assert result.offers_created == 2

    # Verify watermark pointer was updated in store_scraping_pointer
    pointer_stmt = select(StoreScrapingPointer).where(StoreScrapingPointer.store_key == "compumarts")
    ptr_res = await db_session.execute(pointer_stmt)
    ptr = ptr_res.scalar_one_or_none()
    assert ptr is not None
    assert ptr.total_active_offers >= 1

    # Verify audit log in scraping_batch_log
    log_stmt = select(ScrapingBatchLog).where(ScrapingBatchLog.id == result.batch_id)
    log_res = await db_session.execute(log_stmt)
    log = log_res.scalar_one_or_none()
    assert log is not None
    assert log.status == "SUCCESS"
    assert log.items_scraped == 1


@pytest.mark.asyncio
async def test_ingest_from_s3_mocked(db_session: AsyncSession):
    cid = f"test_ingest_s3_{uuid.uuid4().hex[:8]}"
    catalog_dict = {
        "title": "S3 Catalog Test",
        "stores_included": ["compumarts"],
        "laptops": [
            _build_sample_catalog_item(cid, mpn=f"MPN-S3-{uuid.uuid4().hex[:6]}", min_price=52000.0),
        ],
    }

    mock_storage = MagicMock(spec=IObjectStorageService)
    mock_storage.bucket_name = "test-laptop-bucket"
    mock_storage.read_json.return_value = catalog_dict

    service = CatalogIngestionService(storage_service=mock_storage)
    result = await service.ingest_from_s3(
        session=db_session,
        s3_key="catalogs/unified_catalog_latest.json",
        trigger_type="TEST_S3_INGESTION",
    )

    assert result.status == "SUCCESS"
    assert result.total_laptops == 1
    assert result.new_laptops == 1
    mock_storage.read_json.assert_called_once_with("catalogs/unified_catalog_latest.json")

    # Verify laptop inserted
    laptop_stmt = select(LaptopConfiguration).where(LaptopConfiguration.canonical_id == cid)
    laptop_res = await db_session.execute(laptop_stmt)
    assert laptop_res.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_ingest_error_logging_on_invalid_data(db_session: AsyncSession):
    service = CatalogIngestionService()
    # Pass invalid payload without 'laptops' key
    invalid_catalog = {"title": "Invalid Payload"}

    result = await service.ingest_catalog_dict(
        session=db_session,
        catalog_data=invalid_catalog,
        source="test_error_source",
        trigger_type="TEST_ERROR",
    )

    assert result.status == "FAILED"
    assert "Invalid catalog" in str(result.error_message)

    # Verify batch log recorded failure
    log_stmt = select(ScrapingBatchLog).where(ScrapingBatchLog.id == result.batch_id)
    log_res = await db_session.execute(log_stmt)
    log = log_res.scalar_one_or_none()
    assert log is not None
    assert log.status == "FAILED"
    assert log.error_message is not None


@pytest.mark.asyncio
async def test_ingest_from_s3_runs_storage_read_off_event_loop_and_handles_errors(db_session: AsyncSession):
    from unittest.mock import AsyncMock, patch

    mock_storage = MagicMock(spec=IObjectStorageService)
    mock_storage.bucket_name = "test-laptop-bucket"
    mock_storage.read_json.side_effect = FileNotFoundError("NoSuchKey")

    service = CatalogIngestionService(storage_service=mock_storage)
    with patch("app.services.catalog_ingestion_service.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
        mock_to_thread.side_effect = FileNotFoundError("NoSuchKey")
        result = await service.ingest_from_s3(
            session=db_session,
            s3_key="catalogs/missing.json",
            trigger_type="CATALOG_READY_EVENT",
        )

    mock_to_thread.assert_awaited_once_with(mock_storage.read_json, "catalogs/missing.json")
    assert result.status == "FAILED"
    assert "NoSuchKey" in (result.error_message or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_hdr", "expected_hdr"),
    [
        ("HDR", True),
        ("HDR10", True),
        ("Dolby Vision", True),
        ("DisplayHDR 400", True),
        ("No HDR", False),
        ("false", False),
        (None, False),
    ],
)
async def test_seeder_preserves_string_display_hdr_labels(
    db_session: AsyncSession,
    raw_hdr: str | None,
    expected_hdr: bool,
):
    from app.repositories.seeder import CatalogSeederRepository

    cid = f"test_hdr_{uuid.uuid4().hex[:8]}"
    item = _build_sample_catalog_item(cid, mpn=f"MPN-HDR-{uuid.uuid4().hex[:6]}", min_price=50000.0)
    item["specs"]["display"]["hdr"] = raw_hdr

    repo = CatalogSeederRepository(db_session)
    await repo.upsert_catalog({"laptops": [item]})

    row = (
        await db_session.execute(select(LaptopConfiguration).where(LaptopConfiguration.canonical_id == cid))
    ).scalar_one()
    assert row.display_hdr is expected_hdr
