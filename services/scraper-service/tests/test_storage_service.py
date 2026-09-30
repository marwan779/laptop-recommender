from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.core.storage_config import StorageSettings
from app.schemas.laptop import BrandCatalogResult, StoreCatalogResult
from app.schemas.orchestrator import ScrapeRequest, ScrapeTargetResult
from app.services.orchestrator import ScrapeOrchestrator
from app.storage.base import IObjectStorageService
from app.storage.exceptions import (
    StorageConnectionError,
    StorageError,
    StorageNotFoundError,
    StorageOperationError,
    StoragePermissionError,
)
from app.storage.factory import StorageFactory, get_storage_service
from app.storage.models import BatchDeleteResult, ObjectMetadata, ObjectSummary, StorageObject
from app.storage.s3 import S3StorageService


@pytest.fixture
def mock_s3_client():
    return MagicMock()


@pytest.fixture
def storage_settings():
    return StorageSettings(
        storage_provider="s3",
        aws_access_key_id="test_key_id",
        aws_secret_access_key="test_secret",
        aws_region="eu-central-1",
        aws_s3_bucket="test-bucket",
    )


@pytest.fixture
def s3_service(storage_settings, mock_s3_client):
    return S3StorageService(settings=storage_settings, boto3_client=mock_s3_client)


# ── Configuration & Models Tests ─────────────────────────────────────────────


def test_storage_settings_defaults():
    settings = StorageSettings(_env_file=None)
    assert settings.storage_provider == "s3"
    assert settings.aws_region == "eu-central-1"
    assert settings.aws_s3_bucket == "laptop-recommender-raw-catalog"
    assert settings.aws_s3_use_ssl is True


def test_storage_settings_is_configured():
    unconfigured = StorageSettings(aws_access_key_id="", aws_secret_access_key="", aws_s3_endpoint_url=None)
    assert unconfigured.is_configured is False

    configured = StorageSettings(
        aws_access_key_id="key",
        aws_secret_access_key="secret",
        aws_s3_bucket="bucket",
    )
    assert configured.is_configured is True

    localstack_configured = StorageSettings(
        aws_access_key_id="",
        aws_secret_access_key="",
        aws_s3_bucket="bucket",
        aws_s3_endpoint_url="http://localhost:4566",
    )
    assert localstack_configured.is_configured is True


def test_storage_object_helpers():
    data = {"brand": "ASUS", "model": "ZenBook 14"}
    data_bytes = json.dumps(data).encode("utf-8")
    meta = ObjectMetadata(
        key="test.json",
        size_bytes=len(data_bytes),
        content_type="application/json",
        etag="abc123",
        last_modified=datetime.now(timezone.utc),
    )
    obj = StorageObject(key="test.json", bucket="test-bucket", content=data_bytes, metadata=meta)

    assert obj.to_text() == json.dumps(data)
    assert obj.to_json() == data


def test_batch_delete_result_properties():
    res = BatchDeleteResult(deleted_keys=["k1", "k2"], failed_keys=[])
    assert res.total_deleted == 2
    assert res.total_failed == 0
    assert res.is_successful is True

    failed_res = BatchDeleteResult(deleted_keys=["k1"], failed_keys=[{"key": "k2", "message": "AccessDenied"}])
    assert failed_res.total_deleted == 1
    assert failed_res.total_failed == 1
    assert failed_res.is_successful is False


# ── Factory & DIP Tests ──────────────────────────────────────────────────────


def test_storage_factory_creates_s3_service(storage_settings, mock_s3_client):
    service = StorageFactory.create(settings=storage_settings, boto3_client=mock_s3_client)
    assert isinstance(service, S3StorageService)
    assert service.provider_name == "s3"
    assert service.bucket_name == "test-bucket"


def test_storage_factory_unsupported_provider():
    bad_settings = StorageSettings(storage_provider="unsupported_cloud")
    with pytest.raises(ValueError, match="Unsupported storage provider"):
        StorageFactory.create(settings=bad_settings)


def test_storage_factory_open_closed_registration():
    class DummyProvider(IObjectStorageService):
        @property
        def provider_name(self) -> str:
            return "dummy"

        @property
        def bucket_name(self) -> str:
            return "dummy-bucket"

        def upload_file(self, *args, **kwargs): pass
        def upload_bytes(self, *args, **kwargs): pass
        def upload_json(self, *args, **kwargs): pass
        def get_object(self, *args, **kwargs): pass
        def read_bytes(self, *args, **kwargs): pass
        def read_json(self, *args, **kwargs): pass
        def download_file(self, *args, **kwargs): pass
        def exists(self, *args, **kwargs): pass
        def get_metadata(self, *args, **kwargs): pass
        def copy_object(self, *args, **kwargs): pass
        def delete_object(self, *args, **kwargs): pass
        def delete_objects(self, *args, **kwargs): pass
        def list_objects(self, *args, **kwargs): pass
        def generate_presigned_url(self, *args, **kwargs): pass

    StorageFactory.register_provider("dummy", DummyProvider)
    custom_settings = StorageSettings(storage_provider="dummy")
    service = StorageFactory.create(settings=custom_settings)
    assert isinstance(service, DummyProvider)
    assert service.provider_name == "dummy"


# ── S3 CRUD Operations Tests ─────────────────────────────────────────────────


def test_s3_upload_bytes(s3_service, mock_s3_client):
    mock_s3_client.put_object.return_value = {"ETag": '"etag123"'}
    data = b"Hello Object Storage"

    result = s3_service.upload_bytes(
        data=data,
        object_key="folder/hello.txt",
        content_type="text/plain",
        metadata={"author": "laptop-recommender"},
    )

    mock_s3_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="folder/hello.txt",
        Body=data,
        ContentType="text/plain",
        Metadata={"author": "laptop-recommender"},
    )
    assert result.key == "folder/hello.txt"
    assert result.bucket == "test-bucket"
    assert result.content == data
    assert result.metadata.etag == "etag123"
    assert result.metadata.size_bytes == len(data)
    assert result.metadata.content_type == "text/plain"


def test_s3_upload_json(s3_service, mock_s3_client):
    mock_s3_client.put_object.return_value = {"ETag": '"json_etag"'}
    payload = {"brand": "Dell", "laptops_count": 42}

    result = s3_service.upload_json(
        data=payload,
        object_key="catalogs/dell.json",
        metadata={"stage": "level1"},
    )

    assert mock_s3_client.put_object.called
    call_kwargs = mock_s3_client.put_object.call_args.kwargs
    assert call_kwargs["Bucket"] == "test-bucket"
    assert call_kwargs["Key"] == "catalogs/dell.json"
    assert call_kwargs["ContentType"] == "application/json"
    assert json.loads(call_kwargs["Body"].decode("utf-8")) == payload
    assert result.metadata.etag == "json_etag"


def test_s3_upload_file(s3_service, mock_s3_client, tmp_path):
    local_file = tmp_path / "sample.json"
    content = '{"test": 123}'
    local_file.write_text(content, encoding="utf-8")

    mock_s3_client.put_object.return_value = {"ETag": '"file_etag"'}

    result = s3_service.upload_file(
        file_path=local_file,
        object_key="uploads/sample.json",
    )

    assert result.key == "uploads/sample.json"
    assert result.metadata.content_type == "application/json"
    assert result.content == content.encode("utf-8")


def test_s3_upload_file_nonexistent_raises(s3_service):
    with pytest.raises(StorageNotFoundError, match="Local source file does not exist"):
        s3_service.upload_file(file_path="nonexistent_file_path.xyz", object_key="test.xyz")


def test_s3_get_object_and_read(s3_service, mock_s3_client):
    content_bytes = b'{"status": "ok"}'
    mock_body = MagicMock()
    mock_body.read.return_value = content_bytes

    mock_s3_client.get_object.return_value = {
        "Body": mock_body,
        "ContentType": "application/json",
        "ContentLength": len(content_bytes),
        "ETag": '"etag_read"',
        "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "Metadata": {"env": "prod"},
    }

    obj = s3_service.get_object("config.json")
    assert obj.key == "config.json"
    assert obj.content == content_bytes
    assert obj.metadata.content_type == "application/json"
    assert obj.to_json() == {"status": "ok"}


def test_s3_read_bytes_and_json(s3_service, mock_s3_client):
    mock_body = MagicMock()
    mock_body.read.return_value = b'{"key": "value"}'
    mock_s3_client.get_object.return_value = {"Body": mock_body}

    raw = s3_service.read_bytes("test.json")
    assert raw == b'{"key": "value"}'

    parsed = s3_service.read_json("test.json")
    assert parsed == {"key": "value"}


def test_s3_download_file(s3_service, mock_s3_client, tmp_path):
    dest_path = tmp_path / "subfolder" / "downloaded.json"

    def fake_download(bucket, key, filename):
        Path(filename).write_text("downloaded content", encoding="utf-8")

    mock_s3_client.download_file.side_effect = fake_download

    resolved = s3_service.download_file("remote_file.json", dest_path)
    assert resolved == dest_path
    assert dest_path.read_text(encoding="utf-8") == "downloaded content"
    mock_s3_client.download_file.assert_called_once_with("test-bucket", "remote_file.json", str(dest_path))


def test_s3_exists_true_and_false(s3_service, mock_s3_client):
    # Case 1: Object exists
    mock_s3_client.head_object.return_value = {"ContentLength": 100}
    assert s3_service.exists("existing.json") is True

    # Case 2: Object 404 Not Found
    err_response = {"Error": {"Code": "404", "Message": "Not Found"}}
    mock_s3_client.head_object.side_effect = ClientError(err_response, "HeadObject")
    assert s3_service.exists("missing.json") is False


def test_s3_get_metadata(s3_service, mock_s3_client):
    mock_s3_client.head_object.return_value = {
        "ContentLength": 2048,
        "ContentType": "application/pdf",
        "ETag": '"pdf_etag"',
        "LastModified": datetime(2026, 2, 1, tzinfo=timezone.utc),
        "Metadata": {"doc": "manual"},
    }

    meta = s3_service.get_metadata("manual.pdf")
    assert meta.key == "manual.pdf"
    assert meta.size_bytes == 2048
    assert meta.content_type == "application/pdf"
    assert meta.etag == "pdf_etag"
    assert meta.custom_metadata == {"doc": "manual"}


def test_s3_copy_object(s3_service, mock_s3_client):
    mock_s3_client.copy_object.return_value = {"CopyObjectResult": {"ETag": '"copied"'}}
    mock_body = MagicMock()
    mock_body.read.return_value = b"copied content"
    mock_s3_client.get_object.return_value = {
        "Body": mock_body,
        "ContentType": "text/plain",
        "ContentLength": 14,
        "ETag": '"copied"',
    }

    res = s3_service.copy_object("source.txt", "backup/source.txt")
    mock_s3_client.copy_object.assert_called_once_with(
        CopySource={"Bucket": "test-bucket", "Key": "source.txt"},
        Bucket="test-bucket",
        Key="backup/source.txt",
    )
    assert res.key == "backup/source.txt"


def test_s3_delete_object(s3_service, mock_s3_client):
    mock_s3_client.delete_object.return_value = {}
    success = s3_service.delete_object("obsolete.json")
    assert success is True
    mock_s3_client.delete_object.assert_called_once_with(Bucket="test-bucket", Key="obsolete.json")


def test_s3_delete_objects_batch(s3_service, mock_s3_client):
    mock_s3_client.delete_objects.return_value = {
        "Deleted": [{"Key": "k1"}, {"Key": "k2"}],
        "Errors": [{"Key": "k3", "Message": "AccessDenied"}],
    }

    res = s3_service.delete_objects(["k1", "k2", "k3"])
    assert res.total_deleted == 2
    assert res.total_failed == 1
    assert "k1" in res.deleted_keys
    assert res.failed_keys[0]["key"] == "k3"


def test_s3_list_objects(s3_service, mock_s3_client):
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "brands/asus/1.json",
                    "Size": 1024,
                    "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    "ETag": '"e1"',
                },
                {
                    "Key": "brands/asus/2.json",
                    "Size": 2048,
                    "LastModified": datetime(2026, 1, 2, tzinfo=timezone.utc),
                    "ETag": '"e2"',
                },
            ]
        }
    ]
    mock_s3_client.get_paginator.return_value = mock_paginator

    items = s3_service.list_objects(prefix="brands/asus/", max_keys=10)
    assert len(items) == 2
    assert items[0].key == "brands/asus/1.json"
    assert items[0].size_bytes == 1024
    assert items[1].key == "brands/asus/2.json"


def test_s3_generate_presigned_url(s3_service, mock_s3_client):
    mock_s3_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-bucket/doc.pdf?signature=123"

    url = s3_service.generate_presigned_url("doc.pdf", expiration_seconds=1800, http_method="GET")
    mock_s3_client.generate_presigned_url.assert_called_once_with(
        ClientMethod="get_object",
        Params={"Bucket": "test-bucket", "Key": "doc.pdf"},
        ExpiresIn=1800,
    )
    assert url.startswith("https://s3.amazonaws.com/")


# ── Error Mapping Tests ──────────────────────────────────────────────────────


def test_error_mapping_not_found(s3_service, mock_s3_client):
    err = ClientError({"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}}, "GetObject")
    mock_s3_client.get_object.side_effect = err

    with pytest.raises(StorageNotFoundError) as exc_info:
        s3_service.get_object("missing_key.json")
    assert exc_info.value.key == "missing_key.json"
    assert exc_info.value.bucket == "test-bucket"


def test_error_mapping_permission_denied(s3_service, mock_s3_client):
    err = ClientError({"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "PutObject")
    mock_s3_client.put_object.side_effect = err

    with pytest.raises(StoragePermissionError) as exc_info:
        s3_service.upload_bytes(b"data", "secure.json")
    assert exc_info.value.key == "secure.json"


def test_error_mapping_connection_timeout(s3_service, mock_s3_client):
    mock_s3_client.get_object.side_effect = EndpointConnectionError(endpoint_url="https://s3.amazonaws.com")

    with pytest.raises(StorageConnectionError):
        s3_service.read_bytes("data.json")


def test_error_mapping_generic_operation_error(s3_service, mock_s3_client):
    err = ClientError({"Error": {"Code": "InternalError", "Message": "We encountered an internal error."}}, "GetObject")
    mock_s3_client.get_object.side_effect = err

    with pytest.raises(StorageOperationError):
        s3_service.get_object("file.json")


# ── Orchestrator Storage Integration Tests ────────────────────────────────────


@pytest.fixture
def mock_storage_service():
    storage = MagicMock(spec=IObjectStorageService)
    storage.bucket_name = "test-bucket"
    mock_obj = MagicMock(spec=StorageObject)
    mock_obj.key = "brands/brand_asus.json"
    storage.upload_json.return_value = mock_obj
    storage.upload_file.return_value = mock_obj
    return storage


def test_orchestrator_does_not_upload_when_upload_to_bucket_false(mock_storage_service):
    mock_email = MagicMock()
    orchestrator = ScrapeOrchestrator(
        email_service=mock_email,
        storage_service=mock_storage_service,
        upload_to_bucket=False,
    )

    mock_catalog = BrandCatalogResult(
        brand="ASUS",
        official_catalog_url="https://asus.com",
        scrape_mode="level1",
        total_laptops=5,
        total_skipped=0,
        latest_pointers=["Zenbook 14"],
        laptops=[],
    )

    def fake_scrape_brand(key, req):
        return ScrapeTargetResult(
            target_type="brand",
            target_key=key,
            target_name=mock_catalog.brand,
            level=req.level,
            items_scraped=mock_catalog.total_laptops,
            brand_result=mock_catalog,
        )

    with patch.object(orchestrator, "_scrape_brand", side_effect=fake_scrape_brand):
        req = ScrapeRequest(target_type="brand", targets=["asus"], level=1, upload_to_bucket=False)
        response = orchestrator.execute(req)

        assert len(response.results) == 1
        assert response.results[0].storage_key is None
        mock_storage_service.upload_json.assert_not_called()
        mock_storage_service.upload_file.assert_not_called()


def test_orchestrator_uploads_when_constructor_upload_to_bucket_true(mock_storage_service):
    mock_email = MagicMock()
    orchestrator = ScrapeOrchestrator(
        email_service=mock_email,
        storage_service=mock_storage_service,
        upload_to_bucket=True,
    )

    mock_catalog = BrandCatalogResult(
        brand="ASUS",
        official_catalog_url="https://asus.com",
        scrape_mode="level1",
        total_laptops=5,
        total_skipped=0,
        latest_pointers=["Zenbook 14"],
        laptops=[],
    )

    def fake_scrape_brand(key, req):
        return ScrapeTargetResult(
            target_type="brand",
            target_key=key,
            target_name=mock_catalog.brand,
            level=req.level,
            items_scraped=mock_catalog.total_laptops,
            brand_result=mock_catalog,
        )

    with patch.object(orchestrator, "_scrape_brand", side_effect=fake_scrape_brand):
        req = ScrapeRequest(target_type="brand", targets=["asus"], level=1, upload_to_bucket=False)
        response = orchestrator.execute(req)

        assert len(response.results) == 1
        assert response.results[0].storage_key == "brands/brand_asus.json"
        mock_storage_service.upload_json.assert_called_once()
        call_kwargs = mock_storage_service.upload_json.call_args.kwargs
        assert call_kwargs["object_key"] == "brands/brand_asus.json"
        assert call_kwargs["metadata"]["target_key"] == "asus"


def test_orchestrator_uploads_when_request_upload_to_bucket_true(mock_storage_service):
    mock_email = MagicMock()
    orchestrator = ScrapeOrchestrator(
        email_service=mock_email,
        storage_service=mock_storage_service,
        upload_to_bucket=False,  # Constructor False
    )

    mock_store_catalog = StoreCatalogResult(
        store_name="Tradeline",
        store_key="tradeline",
        store_domain="tradelinestores.com",
        total_products=3,
        total_skipped=0,
        products=[],
    )
    mock_obj = MagicMock(spec=StorageObject)
    mock_obj.key = "stores/store_tradeline.json"
    mock_storage_service.upload_json.return_value = mock_obj

    def fake_scrape_store(key, req):
        return ScrapeTargetResult(
            target_type="store",
            target_key=key,
            target_name="Tradeline",
            level=req.level,
            items_scraped=3,
            store_result=mock_store_catalog,
        )

    with patch.object(orchestrator, "_scrape_store", side_effect=fake_scrape_store):
        # Request specifies upload_to_bucket=True
        req = ScrapeRequest(target_type="store", targets=["tradeline"], level=1, upload_to_bucket=True)
        response = orchestrator.execute(req)

        assert len(response.results) == 1
        assert response.results[0].storage_key == "stores/store_tradeline.json"
        mock_storage_service.upload_json.assert_called_once()
        call_kwargs = mock_storage_service.upload_json.call_args.kwargs
        assert call_kwargs["object_key"] == "stores/store_tradeline.json"


def test_orchestrator_upload_happens_before_email():
    """Verify that storage upload is executed before email sending, enriching the report with storage_key."""
    event_order = []
    received_reports = []

    mock_email = MagicMock()

    def fake_email_dispatch(r):
        event_order.append("email")
        received_reports.append(r)

    mock_email.send_scraper_finished_background.side_effect = fake_email_dispatch

    mock_storage = MagicMock(spec=IObjectStorageService)
    mock_storage.bucket_name = "test-bucket"

    def fake_upload(*args, **kwargs):
        event_order.append("storage")
        mock_res = MagicMock(spec=StorageObject)
        mock_res.key = "brands/brand_asus.json"
        return mock_res

    mock_storage.upload_json.side_effect = fake_upload

    orchestrator = ScrapeOrchestrator(
        email_service=mock_email,
        storage_service=mock_storage,
        send_email=True,
        upload_to_bucket=True,
    )

    mock_catalog = BrandCatalogResult(
        brand="ASUS",
        official_catalog_url="https://asus.com",
        scrape_mode="level1",
        total_laptops=5,
        total_skipped=0,
        latest_pointers=["Zenbook 14"],
        laptops=[],
    )

    with patch.object(orchestrator, "_scrape_brand", return_value=ScrapeTargetResult(
        target_type="brand",
        target_key="asus",
        target_name="ASUS",
        level=1,
        items_scraped=5,
        brand_result=mock_catalog,
    )):
        req = ScrapeRequest(target_type="brand", targets=["asus"], level=1, send_email=True, upload_to_bucket=True)
        orchestrator.execute(req)

        assert event_order == ["storage", "email"]
        assert len(received_reports) == 1
        assert received_reports[0].storage_key == "brands/brand_asus.json"


def test_orchestrator_storage_error_is_fail_safe(mock_storage_service):
    """Ensure that an S3 upload failure does not crash the orchestration run."""
    mock_email = MagicMock()
    mock_storage_service.upload_json.side_effect = StorageOperationError("Bucket unavailable")

    orchestrator = ScrapeOrchestrator(
        email_service=mock_email,
        storage_service=mock_storage_service,
        upload_to_bucket=True,
    )

    mock_catalog = BrandCatalogResult(
        brand="ASUS",
        official_catalog_url="https://asus.com",
        scrape_mode="level1",
        total_laptops=5,
        total_skipped=0,
        latest_pointers=["Zenbook 14"],
        laptops=[],
    )

    with patch.object(orchestrator, "_scrape_brand", return_value=ScrapeTargetResult(
        target_type="brand",
        target_key="asus",
        target_name="ASUS",
        level=1,
        items_scraped=5,
        brand_result=mock_catalog,
    )):
        req = ScrapeRequest(target_type="brand", targets=["asus"], level=1, upload_to_bucket=True)
        response = orchestrator.execute(req)

        # Scrape succeeded, but storage_key is None due to handled exception
        assert len(response.results) == 1
        assert response.results[0].storage_key is None
        assert response.results[0].items_scraped == 5


def test_orchestrator_bypasses_output_dir_when_upload_to_bucket_true(mock_storage_service, tmp_path):
    """When upload_to_bucket is True, output_dir should be bypassed and no disk directory/file created."""
    target_dir = tmp_path / "should_not_exist"
    orchestrator = ScrapeOrchestrator(
        storage_service=mock_storage_service,
        upload_to_bucket=True,
    )

    req = ScrapeRequest(
        target_type="brand",
        targets=["asus"],
        level=1,
        output_dir=str(target_dir),
        upload_to_bucket=True,
    )

    out_path = orchestrator._output_path(req, "brand_asus.json")
    assert out_path is None
    assert not target_dir.exists()


def test_orchestrator_creates_output_dir_when_upload_to_bucket_false(mock_storage_service, tmp_path):
    """When upload_to_bucket is False, output_dir is honored and directory is created."""
    target_dir = tmp_path / "local_output"
    orchestrator = ScrapeOrchestrator(
        storage_service=mock_storage_service,
        upload_to_bucket=False,
    )

    req = ScrapeRequest(
        target_type="brand",
        targets=["asus"],
        level=1,
        output_dir=str(target_dir),
        upload_to_bucket=False,
    )

    out_path = orchestrator._output_path(req, "brand_asus.json")
    assert out_path == target_dir / "brand_asus.json"
    assert target_dir.exists()


def test_orchestrator_zero_disk_upload_to_bucket_calls_upload_json(mock_storage_service, tmp_path):
    """End-to-end execute() with upload_to_bucket=True must not write output_file and use upload_json."""
    mock_email = MagicMock()
    mock_obj = MagicMock(spec=StorageObject)
    mock_obj.key = "brands/brand_asus.json"
    mock_storage_service.upload_json.return_value = mock_obj

    orchestrator = ScrapeOrchestrator(
        email_service=mock_email,
        storage_service=mock_storage_service,
        upload_to_bucket=False,
    )

    fake_dir = tmp_path / "ignored_scrape_output"
    mock_catalog = BrandCatalogResult(
        brand="ASUS",
        official_catalog_url="https://asus.com",
        scrape_mode="level1",
        total_laptops=2,
        total_skipped=0,
        latest_pointers=["Zenbook 14"],
        laptops=[],
    )

    # Mock the brand service's scrape() method
    with patch("app.services.orchestrator.BRAND_SERVICE_REGISTRY", {"asus": MagicMock()}):
        mock_brand_service_instance = MagicMock()
        mock_brand_service_instance.scrape.return_value = mock_catalog
        mock_service_cls = MagicMock(return_value=mock_brand_service_instance)
        
        with patch.dict("app.services.orchestrator.BRAND_SERVICE_REGISTRY", {"asus": mock_service_cls}):
            req = ScrapeRequest(
                target_type="brand",
                targets=["asus"],
                level=1,
                output_dir=str(fake_dir),
                upload_to_bucket=True,
            )
            response = orchestrator.execute(req)

            # Assert no local file/dir was created
            assert not fake_dir.exists()
            assert response.results[0].output_file is None
            assert response.results[0].storage_key == "brands/brand_asus.json"

            # Assert upload_json was used directly (in-memory streaming)
            mock_storage_service.upload_json.assert_called_once()
            mock_storage_service.upload_file.assert_not_called()

