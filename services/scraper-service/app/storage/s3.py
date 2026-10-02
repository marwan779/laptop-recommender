from datetime import datetime, UTC
import json
import mimetypes
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ConnectTimeoutError, EndpointConnectionError

from app.core.storage_config import StorageSettings, get_storage_settings
from app.storage.base import IObjectStorageService
from app.storage.exceptions import (
    StorageConnectionError,
    StorageError,
    StorageNotFoundError,
    StorageOperationError,
    StoragePermissionError,
)
from app.storage.models import BatchDeleteResult, ObjectMetadata, ObjectSummary, StorageObject


class S3StorageService(IObjectStorageService):
    """Concrete AWS S3 Object Storage implementation adhering to IObjectStorageService.

    Compatible with standard AWS S3 as well as S3-compliant object stores such as
    MinIO, LocalStack, and Cloudflare R2.
    """

    def __init__(
        self,
        settings: StorageSettings | None = None,
        boto3_client: Any | None = None,
    ) -> None:
        self.settings = settings or get_storage_settings()
        self._bucket = self.settings.aws_s3_bucket

        if boto3_client is not None:
            self._client = boto3_client
        else:
            self._client = self._init_s3_client()

    @property
    def provider_name(self) -> str:
        return "s3"

    @property
    def bucket_name(self) -> str:
        return self._bucket

    def _init_s3_client(self) -> Any:
        """Initialize and configure the boto3 S3 client."""
        client_kwargs: dict[str, Any] = {
            "region_name": self.settings.aws_region or "eu-central-1",
            "config": Config(
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"} if self.settings.aws_s3_force_path_style else {},
            ),
        }

        if self.settings.aws_access_key_id.strip() and self.settings.aws_secret_access_key.strip():
            client_kwargs["aws_access_key_id"] = self.settings.aws_access_key_id.strip()
            client_kwargs["aws_secret_access_key"] = self.settings.aws_secret_access_key.strip()

        if self.settings.aws_s3_endpoint_url and self.settings.aws_s3_endpoint_url.strip():
            client_kwargs["endpoint_url"] = self.settings.aws_s3_endpoint_url.strip()

        if not self.settings.aws_s3_use_ssl:
            client_kwargs["use_ssl"] = False

        try:
            return boto3.session.Session().client("s3", **client_kwargs)
        except Exception as exc:
            raise StorageConnectionError(
                f"Failed to initialize AWS S3 client: {exc}",
                endpoint=self.settings.aws_s3_endpoint_url,
                original_error=exc,
            ) from exc

    def _handle_error(self, exc: Exception, object_key: str | None = None) -> None:
        """Translate botocore / boto3 exceptions into domain storage exceptions."""
        if isinstance(exc, (EndpointConnectionError, ConnectTimeoutError)):
            raise StorageConnectionError(
                f"Network connection error contacting S3 endpoint: {exc}",
                endpoint=self.settings.aws_s3_endpoint_url,
                original_error=exc,
            ) from exc

        if isinstance(exc, ClientError):
            error_code = exc.response.get("Error", {}).get("Code", "")
            http_status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

            if error_code in ("NoSuchKey", "NoSuchBucket", "NotFound", "404") or http_status == 404:
                raise StorageNotFoundError(
                    f"Object '{object_key}' not found in bucket '{self.bucket_name}'.",
                    key=object_key,
                    bucket=self.bucket_name,
                    original_error=exc,
                ) from exc

            if (
                error_code in ("AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403")
                or http_status == 403
            ):
                raise StoragePermissionError(
                    f"Access denied for object '{object_key}' in bucket '{self.bucket_name}'.",
                    key=object_key,
                    bucket=self.bucket_name,
                    original_error=exc,
                ) from exc

            raise StorageOperationError(
                f"S3 operation failed for key '{object_key}': {exc}",
                key=object_key,
                original_error=exc,
            ) from exc

        if isinstance(exc, StorageError):
            raise exc

        raise StorageOperationError(
            f"Unexpected error during storage operation for key '{object_key}': {exc}",
            key=object_key,
            original_error=exc,
        ) from exc

    # ── Create / Upload (C) ──────────────────────────────────────────────

    def upload_file(
        self,
        file_path: str | Path,
        object_key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StorageObject:
        path = Path(file_path)
        if not path.is_file():
            raise StorageNotFoundError(
                f"Local source file does not exist: {file_path}",
                key=object_key,
                bucket=self.bucket_name,
            )

        inferred_type = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        try:
            content = path.read_bytes()
            return self.upload_bytes(
                data=content,
                object_key=object_key,
                content_type=inferred_type,
                metadata=metadata,
            )
        except Exception as exc:
            self._handle_error(exc, object_key)
            raise

    def upload_bytes(
        self,
        data: bytes,
        object_key: str,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> StorageObject:
        put_kwargs: dict[str, Any] = {
            "Bucket": self.bucket_name,
            "Key": object_key,
            "Body": data,
            "ContentType": content_type,
        }
        if metadata:
            put_kwargs["Metadata"] = {str(k): str(v) for k, v in metadata.items()}

        try:
            resp = self._client.put_object(**put_kwargs)
            etag = resp.get("ETag", "").strip('"')
            obj_meta = ObjectMetadata(
                key=object_key,
                size_bytes=len(data),
                content_type=content_type,
                etag=etag,
                last_modified=datetime.now(UTC),
                custom_metadata=metadata or {},
            )
            return StorageObject(
                key=object_key,
                bucket=self.bucket_name,
                content=data,
                metadata=obj_meta,
            )
        except Exception as exc:
            self._handle_error(exc, object_key)
            raise

    def upload_json(
        self,
        data: Any,
        object_key: str,
        metadata: dict[str, str] | None = None,
    ) -> StorageObject:
        try:
            json_bytes = json.dumps(data, indent=2, default=str, ensure_ascii=False).encode("utf-8")
            return self.upload_bytes(
                data=json_bytes,
                object_key=object_key,
                content_type="application/json",
                metadata=metadata,
            )
        except Exception as exc:
            self._handle_error(exc, object_key)
            raise

    # ── Read / Retrieve (R) ──────────────────────────────────────────────

    def get_object(self, object_key: str) -> StorageObject:
        try:
            resp = self._client.get_object(Bucket=self.bucket_name, Key=object_key)
            content = resp["Body"].read()
            etag = resp.get("ETag", "").strip('"')
            content_type = resp.get("ContentType", "application/octet-stream")
            last_modified = resp.get("LastModified")
            custom_metadata = resp.get("Metadata", {})

            obj_meta = ObjectMetadata(
                key=object_key,
                size_bytes=len(content),
                content_type=content_type,
                etag=etag,
                last_modified=last_modified,
                custom_metadata=custom_metadata,
            )
            return StorageObject(
                key=object_key,
                bucket=self.bucket_name,
                content=content,
                metadata=obj_meta,
            )
        except Exception as exc:
            self._handle_error(exc, object_key)
            raise

    def read_bytes(self, object_key: str) -> bytes:
        try:
            resp = self._client.get_object(Bucket=self.bucket_name, Key=object_key)
            return resp["Body"].read()
        except Exception as exc:
            self._handle_error(exc, object_key)
            raise

    def read_json(self, object_key: str) -> Any:
        raw_bytes = self.read_bytes(object_key)
        try:
            return json.loads(raw_bytes.decode("utf-8"))
        except Exception as exc:
            raise StorageOperationError(
                f"Failed to deserialize JSON content for object '{object_key}': {exc}",
                key=object_key,
                original_error=exc,
            ) from exc

    def download_file(self, object_key: str, destination_path: str | Path) -> Path:
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client.download_file(self.bucket_name, object_key, str(dest))
            return dest
        except Exception as exc:
            self._handle_error(exc, object_key)
            raise

    def exists(self, object_key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            http_status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if error_code in ("NoSuchKey", "NotFound", "404") or http_status == 404:
                return False
            self._handle_error(exc, object_key)
            return False
        except Exception as exc:
            self._handle_error(exc, object_key)
            return False

    def get_metadata(self, object_key: str) -> ObjectMetadata:
        try:
            resp = self._client.head_object(Bucket=self.bucket_name, Key=object_key)
            return ObjectMetadata(
                key=object_key,
                size_bytes=resp.get("ContentLength", 0),
                content_type=resp.get("ContentType", "application/octet-stream"),
                etag=resp.get("ETag", "").strip('"'),
                last_modified=resp.get("LastModified"),
                custom_metadata=resp.get("Metadata", {}),
            )
        except Exception as exc:
            self._handle_error(exc, object_key)
            raise

    # ── Update / Copy (U) ────────────────────────────────────────────────

    def copy_object(self, source_key: str, destination_key: str) -> StorageObject:
        try:
            copy_source = {"Bucket": self.bucket_name, "Key": source_key}
            self._client.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=destination_key,
            )
            return self.get_object(destination_key)
        except Exception as exc:
            self._handle_error(exc, source_key)
            raise

    # ── Delete (D) ───────────────────────────────────────────────────────

    def delete_object(self, object_key: str) -> bool:
        try:
            self._client.delete_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except Exception as exc:
            self._handle_error(exc, object_key)
            raise

    def delete_objects(self, object_keys: list[str]) -> BatchDeleteResult:
        if not object_keys:
            return BatchDeleteResult()

        deleted: list[str] = []
        failed: list[dict[str, str]] = []

        chunk_size = 1000
        for i in range(0, len(object_keys), chunk_size):
            chunk = object_keys[i : i + chunk_size]
            delete_payload = {"Objects": [{"Key": k} for k in chunk], "Quiet": False}
            try:
                resp = self._client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete=delete_payload,
                )
                for item in resp.get("Deleted", []):
                    deleted.append(item["Key"])
                for err in resp.get("Errors", []):
                    failed.append({"key": err.get("Key", ""), "message": err.get("Message", "")})
            except Exception as exc:
                self._handle_error(exc, str(chunk))

        return BatchDeleteResult(deleted_keys=deleted, failed_keys=failed)

    # ── List / Query ─────────────────────────────────────────────────────

    def list_objects(self, prefix: str = "", max_keys: int = 1000) -> list[ObjectSummary]:
        summaries: list[ObjectSummary] = []
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=prefix,
                PaginationConfig={"MaxItems": max_keys},
            )
            for page in page_iterator:
                for item in page.get("Contents", []):
                    summaries.append(
                        ObjectSummary(
                            key=item["Key"],
                            size_bytes=item["Size"],
                            last_modified=item.get("LastModified"),
                            etag=item.get("ETag", "").strip('"'),
                        )
                    )
            return summaries
        except Exception as exc:
            self._handle_error(exc, prefix)
            raise

    # ── Presigned URLs ───────────────────────────────────────────────────

    def generate_presigned_url(
        self,
        object_key: str,
        expiration_seconds: int = 3600,
        http_method: str = "GET",
    ) -> str:
        method_map = {
            "GET": "get_object",
            "PUT": "put_object",
            "HEAD": "head_object",
            "DELETE": "delete_object",
        }
        client_method = method_map.get(http_method.upper(), "get_object")
        try:
            return self._client.generate_presigned_url(
                ClientMethod=client_method,
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=expiration_seconds,
            )
        except Exception as exc:
            self._handle_error(exc, object_key)
            raise
