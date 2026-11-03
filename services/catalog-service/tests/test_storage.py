from datetime import UTC, datetime
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import MagicMock

from botocore.exceptions import ClientError, EndpointConnectionError
import pytest

from app.common.storage import (
    IObjectStorageService,
    ObjectMetadata,
    S3StorageService,
    StorageConnectionError,
    StorageFactory,
    StorageNotFoundError,
    StoragePermissionError,
    StorageSettings,
)


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
        aws_s3_bucket="test-catalog-bucket",
    )


@pytest.fixture
def s3_service(storage_settings, mock_s3_client):
    return S3StorageService(settings=storage_settings, boto3_client=mock_s3_client)


def test_storage_settings_configuration():
    configured = StorageSettings(
        aws_access_key_id="key",
        aws_secret_access_key="secret",
        aws_s3_bucket="bucket",
    )
    assert configured.is_configured is True
    assert configured.storage_provider == "s3"

    unconfigured = StorageSettings(aws_access_key_id="", aws_secret_access_key="", aws_s3_endpoint_url=None)
    assert unconfigured.is_configured is False


def test_storage_factory_resolution(storage_settings, mock_s3_client):
    service = StorageFactory.create(settings=storage_settings, boto3_client=mock_s3_client)
    assert isinstance(service, IObjectStorageService)
    assert service.provider_name == "s3"
    assert service.bucket_name == "test-catalog-bucket"


def test_upload_and_read_json(s3_service, mock_s3_client):
    mock_s3_client.put_object.return_value = {"ETag": '"etag123"'}
    test_data = {"laptops": [{"id": "laptop-1", "price": 45000}]}

    obj = s3_service.upload_json(data=test_data, object_key="catalogs/test.json")
    assert obj.key == "catalogs/test.json"
    assert obj.bucket == "test-catalog-bucket"
    assert obj.to_json() == test_data
    mock_s3_client.put_object.assert_called_once()

    # Read JSON
    mock_body = BytesIO(json.dumps(test_data).encode("utf-8"))
    mock_s3_client.get_object.return_value = {
        "Body": mock_body,
        "ETag": '"etag123"',
        "ContentType": "application/json",
        "LastModified": datetime.now(UTC),
    }

    retrieved = s3_service.read_json("catalogs/test.json")
    assert retrieved == test_data


def test_exists_and_metadata(s3_service, mock_s3_client):
    mock_s3_client.head_object.return_value = {
        "ContentLength": 1024,
        "ContentType": "application/json",
        "ETag": '"etag_abc"',
        "LastModified": datetime.now(UTC),
        "Metadata": {"version": "1.0"},
    }

    assert s3_service.exists("catalogs/active.json") is True
    meta = s3_service.get_metadata("catalogs/active.json")
    assert isinstance(meta, ObjectMetadata)
    assert meta.size_bytes == 1024
    assert meta.custom_metadata.get("version") == "1.0"


def test_not_found_exception_handling(s3_service, mock_s3_client):
    mock_s3_client.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
        "GetObject",
    )

    with pytest.raises(StorageNotFoundError) as exc_info:
        s3_service.get_object("nonexistent.json")
    assert exc_info.value.key == "nonexistent.json"


def test_permission_error_handling(s3_service, mock_s3_client):
    mock_s3_client.get_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
        "GetObject",
    )

    with pytest.raises(StoragePermissionError):
        s3_service.get_object("secret.json")


def test_connection_error_handling(s3_service, mock_s3_client):
    mock_s3_client.get_object.side_effect = EndpointConnectionError(endpoint_url="https://s3.amazonaws.com")

    with pytest.raises(StorageConnectionError):
        s3_service.get_object("network_down.json")


def test_batch_delete_objects(s3_service, mock_s3_client):
    mock_s3_client.delete_objects.return_value = {
        "Deleted": [{"Key": "item1.json"}, {"Key": "item2.json"}],
        "Errors": [],
    }

    result = s3_service.delete_objects(["item1.json", "item2.json"])
    assert result.is_successful is True
    assert result.total_deleted == 2
    assert "item1.json" in result.deleted_keys


def test_generate_presigned_url(s3_service, mock_s3_client):
    mock_s3_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-bucket/item.json?token=123"

    url = s3_service.generate_presigned_url("item.json", expiration_seconds=600)
    assert "https://" in url
    mock_s3_client.generate_presigned_url.assert_called_once()
