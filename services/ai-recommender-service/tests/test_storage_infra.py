"""Tests for the S3 / S3-compatible object storage abstraction."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.common.storage import (
    BatchDeleteResult,
    S3StorageService,
    StorageConnectionError,
    StorageFactory,
    StorageNotFoundError,
    StorageObject,
    StorageOperationError,
    StoragePermissionError,
)
from app.core.storage_config import StorageSettings


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakePaginator:
    def __init__(self, client: "_FakeBoto3Client") -> None:
        self._client = client

    def paginate(self, **kwargs: Any):
        self._client.paginate_calls.append(kwargs)
        return self._client.pages


class _FakeBoto3Client:
    """In-memory boto3 S3 client double."""

    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.delete_batches: list[list[str]] = []
        self.pages: list[dict[str, Any]] = []
        self.paginate_calls: list[dict[str, Any]] = []
        self.download_calls: list[tuple[str, str, str]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        self.objects[key] = {
            "Body": kwargs["Body"],
            "ContentType": kwargs.get("ContentType", "application/octet-stream"),
            "Metadata": dict(kwargs.get("Metadata", {})),
            "ETag": f'"etag-{key}"',
            "LastModified": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        }
        return {"ETag": f'"etag-{key}"'}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        if key == "forbidden/object":
            raise ClientError(
                {
                    "Error": {"Code": "AccessDenied", "Message": "Denied"},
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                "GetObject",
            )
        if key == "offline/object":
            raise EndpointConnectionError(endpoint_url="https://fake-endpoint")
        if key not in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "NoSuchKey", "Message": "Missing"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "GetObject",
            )
        stored = self.objects[key]
        return {
            "Body": _FakeBody(stored["Body"]),
            "ContentType": stored["ContentType"],
            "ETag": stored["ETag"],
            "LastModified": stored["LastModified"],
            "Metadata": stored["Metadata"],
        }

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        if key == "forbidden/object":
            raise ClientError(
                {
                    "Error": {"Code": "AccessDenied", "Message": "Denied"},
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                "HeadObject",
            )
        if key not in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "NoSuchKey", "Message": "Missing"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "HeadObject",
            )
        stored = self.objects[key]
        return {
            "ContentLength": len(stored["Body"]),
            "ContentType": stored["ContentType"],
            "ETag": stored["ETag"],
            "LastModified": stored["LastModified"],
            "Metadata": stored["Metadata"],
        }

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.objects.pop(kwargs["Key"], None)
        return {}

    def delete_objects(self, **kwargs: Any) -> dict[str, Any]:
        keys = [item["Key"] for item in kwargs["Delete"]["Objects"]]
        self.delete_batches.append(keys)
        deleted = []
        errors = []
        for key in keys:
            if key.startswith("bad/"):
                errors.append({"Key": key, "Message": "Rejected"})
            else:
                self.objects.pop(key, None)
                deleted.append({"Key": key})
        return {"Deleted": deleted, "Errors": errors}

    def get_paginator(self, name: str) -> _FakePaginator:
        assert name == "list_objects_v2"
        return _FakePaginator(self)

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        self.download_calls.append((bucket, key, destination))
        with open(destination, "wb") as handle:
            handle.write(self.objects[key]["Body"])

    def copy_object(self, **kwargs: Any) -> dict[str, Any]:
        source = kwargs["CopySource"]["Key"]
        self.objects[kwargs["Key"]] = dict(self.objects[source])
        return {}

    def generate_presigned_url(self, **kwargs: Any) -> str:
        return f"https://fake/{kwargs['Params']['Key']}?method={kwargs['ClientMethod']}"


def _settings(**overrides: Any) -> StorageSettings:
    values: dict[str, Any] = {
        "storage_provider": "s3",
        "aws_access_key_id": "test-key",
        "aws_secret_access_key": "test-secret",
        "aws_region": "eu-central-1",
        "aws_s3_bucket": "test-bucket",
        "aws_s3_endpoint_url": None,
        "aws_s3_use_ssl": True,
        "aws_s3_force_path_style": False,
    }
    values.update(overrides)
    return StorageSettings(**values)


def _service(client: _FakeBoto3Client | None = None) -> tuple[S3StorageService, _FakeBoto3Client]:
    fake = client or _FakeBoto3Client()
    return S3StorageService(settings=_settings(), boto3_client=fake), fake


def test_upload_json_and_read_json_round_trip_utf8() -> None:
    service, fake = _service()
    payload = {
        "title": "لابتوب للألعاب",
        "nested": {"score": 91.5},
        "pros": ["تبريد ممتاز", "شاشة مشرقة"],
    }

    uploaded = service.upload_json(payload, "reviews/laptop.json", metadata={"source": "test"})

    expected_bytes = json.dumps(payload, indent=2, default=str, ensure_ascii=False).encode("utf-8")
    assert isinstance(uploaded, StorageObject)
    assert uploaded.content == expected_bytes
    assert fake.objects["reviews/laptop.json"]["Body"] == expected_bytes
    assert b"\\u0644" not in expected_bytes
    assert "لابتوب للألعاب".encode("utf-8") in expected_bytes
    assert uploaded.metadata.content_type == "application/json"
    assert uploaded.metadata.custom_metadata == {"source": "test"}
    assert uploaded.metadata.size_bytes == len(expected_bytes)

    assert service.read_json("reviews/laptop.json") == payload


def test_get_object_and_read_bytes_return_payload() -> None:
    service, _ = _service()
    service.upload_bytes(
        b"raw-bytes",
        "raw/sample.bin",
        content_type="application/octet-stream",
        metadata={"kind": "scrape"},
    )

    retrieved = service.get_object("raw/sample.bin")
    assert retrieved.key == "raw/sample.bin"
    assert retrieved.bucket == "test-bucket"
    assert retrieved.content == b"raw-bytes"
    assert retrieved.metadata.content_type == "application/octet-stream"
    assert retrieved.metadata.custom_metadata == {"kind": "scrape"}

    assert service.read_bytes("raw/sample.bin") == b"raw-bytes"


def test_exists_true_and_false_on_missing_key() -> None:
    service, _ = _service()
    service.upload_bytes(b"present", "raw/present.json")

    assert service.exists("raw/present.json") is True
    assert service.exists("raw/missing.json") is False


def test_error_translation() -> None:
    service, _ = _service()

    with pytest.raises(StorageNotFoundError) as missing:
        service.get_object("missing/object.json")
    assert missing.value.key == "missing/object.json"
    assert missing.value.bucket == "test-bucket"

    with pytest.raises(StoragePermissionError) as denied:
        service.get_object("forbidden/object")
    assert denied.value.key == "forbidden/object"

    with pytest.raises(StorageConnectionError):
        service.get_object("offline/object")

    service.upload_bytes(b"{not valid json", "raw/broken.json")
    with pytest.raises(StorageOperationError) as invalid_json:
        service.read_json("raw/broken.json")
    assert invalid_json.value.key == "raw/broken.json"


def test_delete_objects_batches_in_chunks_of_1000() -> None:
    service, fake = _service()
    keys = ["bad/0"] + [f"raw/item-{index}.json" for index in range(1004)]

    result = service.delete_objects(keys)

    assert isinstance(result, BatchDeleteResult)
    assert [len(batch) for batch in fake.delete_batches] == [1000, 5]
    assert fake.delete_batches[0][0] == "bad/0"
    assert result.total_deleted == 1004
    assert result.total_failed == 1
    assert result.failed_keys == [{"key": "bad/0", "message": "Rejected"}]
    assert result.is_successful is False

    assert service.delete_objects([]).total_deleted == 0


def test_list_objects_uses_paginator_and_returns_summaries() -> None:
    service, fake = _service()
    first_modified = datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)
    fake.pages = [
        {
            "Contents": [
                {
                    "Key": "reviews/a.json",
                    "Size": 101,
                    "LastModified": first_modified,
                    "ETag": '"etag-a"',
                }
            ]
        },
        {
            "Contents": [
                {
                    "Key": "reviews/b.json",
                    "Size": 202,
                    "LastModified": None,
                    "ETag": '"etag-b"',
                }
            ]
        },
    ]

    summaries = service.list_objects(prefix="reviews/", max_keys=50)

    assert [summary.key for summary in summaries] == ["reviews/a.json", "reviews/b.json"]
    assert summaries[0].size_bytes == 101
    assert summaries[0].last_modified == first_modified
    assert summaries[0].etag == "etag-a"
    assert summaries[1].etag == "etag-b"
    assert fake.paginate_calls == [
        {
            "Bucket": "test-bucket",
            "Prefix": "reviews/",
            "PaginationConfig": {"MaxItems": 50},
        }
    ]


def test_storage_factory_create_and_invalid_provider() -> None:
    fake = _FakeBoto3Client()
    service = StorageFactory.create(settings=_settings(), boto3_client=fake)

    assert isinstance(service, S3StorageService)
    assert service.provider_name == "s3"
    assert service.bucket_name == "test-bucket"

    invalid = _settings(storage_provider="gcs")
    with pytest.raises(ValueError, match="Unsupported storage provider 'gcs'"):
        StorageFactory.create(settings=invalid, boto3_client=fake)


def test_storage_settings_is_configured_combinations() -> None:
    empty = StorageSettings(
        aws_s3_bucket="",
        aws_access_key_id="",
        aws_secret_access_key="",
        aws_s3_endpoint_url=None,
    )
    assert empty.is_configured is False

    bucket_only = StorageSettings(
        aws_s3_bucket="bucket",
        aws_access_key_id="",
        aws_secret_access_key="",
        aws_s3_endpoint_url=None,
    )
    assert bucket_only.is_configured is False

    credentials = StorageSettings(
        aws_s3_bucket="bucket",
        aws_access_key_id="key",
        aws_secret_access_key="secret",
        aws_s3_endpoint_url=None,
    )
    assert credentials.is_configured is True

    endpoint = StorageSettings(
        aws_s3_bucket="bucket",
        aws_access_key_id="",
        aws_secret_access_key="",
        aws_s3_endpoint_url="http://localhost:4566",
    )
    assert endpoint.is_configured is True

    half_credentials = StorageSettings(
        aws_s3_bucket="bucket",
        aws_access_key_id="key",
        aws_secret_access_key="",
        aws_s3_endpoint_url=None,
    )
    assert half_credentials.is_configured is False
