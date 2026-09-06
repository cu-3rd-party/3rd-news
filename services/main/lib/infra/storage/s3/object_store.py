from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import PurePath
from typing import Any, Final
from urllib.parse import quote

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError
from lib.dto.byte_range import ByteRange
from lib.dto.completed_object import CompletedObject
from lib.dto.object_info import ObjectInfo
from lib.dto.presigned_upload import PresignedUpload
from lib.interactor.errors.object_integrity import ObjectIntegrityError
from lib.interactor.interfaces.storage.object_store import ObjectStore

_RANGE_PATTERN: Final = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_range_header(value: str | None, size: int) -> ByteRange | None:
    if value is None:
        return None
    match = _RANGE_PATTERN.fullmatch(value.strip())
    if match is None or size < 0:
        raise ValueError("invalid Range header")
    raw_start, raw_end = match.groups()
    if not raw_start and not raw_end:
        raise ValueError("invalid Range header")
    if not raw_start:
        suffix = int(raw_end)
        if suffix < 1:
            raise ValueError("invalid suffix range")
        start = max(size - suffix, 0)
        end = size - 1
    else:
        start = int(raw_start)
        end = size - 1 if not raw_end else int(raw_end)
    if start >= size or end < start:
        raise ValueError("range is not satisfiable")
    return ByteRange(start=start, end=min(end, size - 1), size=size)


class S3ObjectStore(ObjectStore):
    def __init__(
        self,
        *,
        endpoint_url: str,
        public_endpoint_url: str | None = None,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        presign_ttl_seconds: int = 900,
        max_upload_bytes: int = 50_000_000,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._public_endpoint_url = public_endpoint_url or endpoint_url
        self._bucket = bucket
        self._region = region
        self._ttl = presign_ttl_seconds
        self._max_upload_bytes = max_upload_bytes
        self._session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
        )

    async def delete(self, key: str) -> None:
        async with self._client() as client:
            await client.delete_object(Bucket=self._bucket, Key=key)

    async def objects_before(self, cutoff: datetime) -> AsyncIterator[str]:
        async with self._client() as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket):
                for item in page.get("Contents", []):
                    if item["LastModified"] < cutoff:
                        yield item["Key"]

    async def create_upload(
        self,
        *,
        owner_id: str,
        intent_id: str,
        size: int,
        content_type: str,
        sha256: str,
    ) -> PresignedUpload:
        self._validate_intent(size=size, content_type=content_type, sha256=sha256)
        key = f"tmp/{quote(owner_id, safe='')}/{quote(intent_id, safe='')}/{uuid.uuid4().hex}"
        metadata = {
            "owner-id": owner_id,
            "upload-intent-id": intent_id,
            "sha256": sha256.lower(),
            "expected-size": str(size),
        }
        params = {
            "Bucket": self._bucket,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": size,
            "Metadata": metadata,
        }
        async with self._client(endpoint_url=self._public_endpoint_url) as client:
            url = await client.generate_presigned_url(
                "put_object", Params=params, ExpiresIn=self._ttl, HttpMethod="PUT"
            )
        headers = {"Content-Type": content_type}
        headers.update({f"x-amz-meta-{name}": value for name, value in metadata.items()})
        return PresignedUpload(url=url, key=key, headers=headers, expires_in=self._ttl)

    async def presign_put(self, **kwargs: Any) -> PresignedUpload:
        return await self.create_upload(**kwargs)

    async def complete_upload(
        self,
        *,
        temporary_key: str,
        owner_id: str,
        intent_id: str,
        expected_size: int,
        expected_content_type: str,
        expected_sha256: str,
    ) -> CompletedObject:
        if not temporary_key.startswith(
            f"tmp/{quote(owner_id, safe='')}/{quote(intent_id, safe='')}/"
        ):
            raise ObjectIntegrityError("temporary key does not belong to this upload intent")
        expected_sha256 = expected_sha256.lower()
        self._validate_intent(
            size=expected_size,
            content_type=expected_content_type,
            sha256=expected_sha256,
        )
        info = await self.inspect_and_hash(temporary_key)
        metadata = {key.lower(): value for key, value in info.metadata.items()}
        expected_metadata = {
            "owner-id": owner_id,
            "upload-intent-id": intent_id,
            "sha256": expected_sha256,
            "expected-size": str(expected_size),
        }
        if any(metadata.get(key) != value for key, value in expected_metadata.items()):
            raise ObjectIntegrityError("object metadata does not match the upload intent")
        if info.size != expected_size:
            raise ObjectIntegrityError("object size does not match the upload intent")
        if info.content_type.split(";", 1)[0].lower() != expected_content_type.lower():
            raise ObjectIntegrityError("object content type does not match the upload intent")
        if info.sha256 != expected_sha256:
            raise ObjectIntegrityError("object digest does not match the upload intent")

        final_key = f"objects/{expected_sha256[:2]}/{expected_sha256}/{uuid.uuid4().hex}"
        copy_metadata = {
            "owner-id": owner_id,
            "upload-intent-id": intent_id,
            "sha256": expected_sha256,
            "size": str(expected_size),
        }
        async with self._client() as client:
            await client.copy_object(
                Bucket=self._bucket,
                Key=final_key,
                CopySource={"Bucket": self._bucket, "Key": temporary_key},
                MetadataDirective="REPLACE",
                Metadata=copy_metadata,
                ContentType=expected_content_type,
            )
            final = await self.inspect_and_hash(final_key)
            if final.size != expected_size or final.sha256 != expected_sha256:
                await client.delete_object(Bucket=self._bucket, Key=final_key)
                raise ObjectIntegrityError(
                    "immutable copy size or digest changed during upload completion"
                )
            await client.delete_object(Bucket=self._bucket, Key=temporary_key)
        return CompletedObject(
            key=final_key,
            source_key=temporary_key,
            size=expected_size,
            content_type=expected_content_type,
            sha256=expected_sha256,
            metadata=copy_metadata,
        )

    async def promote(self, **kwargs: Any) -> CompletedObject:
        return await self.complete_upload(**kwargs)

    async def inspect_and_hash(self, key: str) -> ObjectInfo:
        digest = hashlib.sha256()
        total = 0
        async with self._client() as client:
            response = await client.get_object(Bucket=self._bucket, Key=key)
            declared = int(response["ContentLength"])
            if declared > self._max_upload_bytes:
                raise ObjectIntegrityError("object exceeds the upload limit")
            body = response["Body"]
            try:
                while chunk := await body.read(64 * 1024):
                    total += len(chunk)
                    if total > self._max_upload_bytes:
                        raise ObjectIntegrityError("object exceeds the upload limit")
                    digest.update(chunk)
            finally:
                body.close()
        if total != declared:
            raise ObjectIntegrityError("object ended before its declared size")
        return ObjectInfo(
            key=key,
            size=total,
            content_type=str(response.get("ContentType") or "application/octet-stream"),
            sha256=digest.hexdigest(),
            metadata=dict(response.get("Metadata") or {}),
        )

    async def put_bytes(
        self,
        data: bytes,
        *,
        content_type: str,
        owner_id: str,
        source_id: str,
    ) -> ObjectInfo:
        if len(data) > self._max_upload_bytes:
            raise ObjectIntegrityError("object exceeds the upload limit")
        if not content_type or "\r" in content_type or "\n" in content_type:
            raise ValueError("invalid content type")
        digest = hashlib.sha256(data).hexdigest()
        key = f"objects/{digest[:2]}/{digest}/{uuid.uuid4().hex}"
        metadata = {
            "owner-id": owner_id,
            "source-id": source_id,
            "sha256": digest,
            "size": str(len(data)),
        }
        async with self._client() as client:
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentLength=len(data),
                ContentType=content_type,
                Metadata=metadata,
            )
        return ObjectInfo(key, len(data), content_type, digest, metadata)

    async def stat(self, key: str) -> ObjectInfo:
        async with self._client() as client:
            response = await client.head_object(Bucket=self._bucket, Key=key)
        metadata = dict(response.get("Metadata") or {})
        return ObjectInfo(
            key=key,
            size=int(response["ContentLength"]),
            content_type=str(response.get("ContentType") or "application/octet-stream"),
            sha256=metadata.get("sha256", ""),
            metadata=metadata,
        )

    async def iter_object(
        self, key: str, *, byte_range: ByteRange | None = None
    ) -> AsyncIterator[bytes]:
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        if byte_range is not None:
            params["Range"] = f"bytes={byte_range.start}-{byte_range.end}"
        async with self._client() as client:
            response = await client.get_object(**params)
            body = response["Body"]
            try:
                while chunk := await body.read(64 * 1024):
                    yield chunk
            finally:
                body.close()

    def read(self, key: str, *, byte_range: ByteRange | None = None) -> AsyncIterator[bytes]:
        return self.iter_object(key, byte_range=byte_range)

    async def ready(self) -> None:
        async with self._client() as client:
            await client.head_bucket(Bucket=self._bucket)

    async def close(self) -> None:

        return None

    async def exists(self, key: str) -> bool:
        try:
            await self.stat(key)
        except ClientError as exc:
            status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            if status == 404:
                return False
            raise
        return True

    def content_disposition(self, filename: str | None) -> str:
        safe_name = PurePath(filename or "attachment").name.replace("\x00", "")[:200]
        ascii_name = "".join(
            ch if 32 <= ord(ch) < 127 and ch not in {'"', "\\"} else "_" for ch in safe_name
        )
        encoded = quote(safe_name, safe="")
        return f"attachment; filename=\"{ascii_name or 'attachment'}\"; filename*=UTF-8''{encoded}"

    def _client(self, *, endpoint_url: str | None = None) -> Any:
        return self._session.client(
            "s3",
            endpoint_url=endpoint_url or self._endpoint_url,
            region_name=self._region,
            config=self._config,
        )

    def _validate_intent(self, *, size: int, content_type: str, sha256: str) -> None:
        if size < 0 or size > self._max_upload_bytes:
            raise ValueError("invalid upload size")
        if not content_type or "\r" in content_type or "\n" in content_type:
            raise ValueError("invalid content type")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
            raise ValueError("sha256 must be 64 hexadecimal characters")
