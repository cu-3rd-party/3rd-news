from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager

import pytest
from lib.infra.storage.s3 import ObjectInfo, S3ObjectStore
from lib.interactor.errors.object_integrity import ObjectIntegrityError


@pytest.mark.asyncio
async def test_upload_completion_rejects_same_size_swap_after_hash(monkeypatch) -> None:
    good = b"trusted"
    replacement = b"hostile"
    assert len(good) == len(replacement)
    expected_digest = hashlib.sha256(good).hexdigest()
    temporary_key = "tmp/owner/intent/upload"
    objects = {temporary_key: good}
    deleted: list[str] = []

    class Client:
        async def copy_object(self, *, Bucket, Key, CopySource, **kwargs):
            del Bucket, kwargs
            objects[Key] = objects[CopySource["Key"]]

        async def head_object(self, *, Bucket, Key):
            del Bucket
            return {"ContentLength": len(objects[Key])}

        async def delete_object(self, *, Bucket, Key):
            del Bucket
            deleted.append(Key)
            objects.pop(Key, None)

    store = S3ObjectStore(
        endpoint_url="http://file.internal",
        bucket="qa",
        access_key="qa",
        secret_key="qa",
    )
    swapped = False

    async def inspect_and_swap(key: str) -> ObjectInfo:
        nonlocal swapped
        body = objects[key]
        result = ObjectInfo(
            key=key,
            size=len(body),
            content_type="application/octet-stream",
            sha256=hashlib.sha256(body).hexdigest(),
            metadata={
                "owner-id": "owner",
                "upload-intent-id": "intent",
                "sha256": expected_digest,
                "expected-size": str(len(good)),
            },
        )
        if key == temporary_key and not swapped:
            swapped = True
            objects[key] = replacement
        return result

    @asynccontextmanager
    async def client(**kwargs):
        del kwargs
        yield Client()

    monkeypatch.setattr(store, "inspect_and_hash", inspect_and_swap)
    monkeypatch.setattr(store, "_client", client)

    with pytest.raises(ObjectIntegrityError, match="immutable copy|digest|changed"):
        await store.complete_upload(
            temporary_key=temporary_key,
            owner_id="owner",
            intent_id="intent",
            expected_size=len(good),
            expected_content_type="application/octet-stream",
            expected_sha256=expected_digest,
        )
    assert any(key.startswith("objects/") for key in deleted)


@pytest.mark.asyncio
async def test_presign_binds_actual_http_content_length(monkeypatch):
    seen = {}

    class Client:
        async def generate_presigned_url(self, operation, *, Params, ExpiresIn, HttpMethod):
            seen.update(Params)
            return "https://uploads.example.edu/fixture"

    @asynccontextmanager
    async def client(**kwargs):
        yield Client()

    store = S3ObjectStore(
        endpoint_url="http://file.internal", bucket="qa", access_key="qa", secret_key="qa"
    )
    monkeypatch.setattr(store, "_client", client)
    await store.create_upload(
        owner_id="qa", intent_id="intent", size=7, content_type="text/plain", sha256="a" * 64
    )
    assert seen["ContentLength"] == 7


@pytest.mark.asyncio
async def test_completed_upload_replay_preserves_contract_fields():
    from types import SimpleNamespace
    from typing import Any, cast
    from uuid import uuid4

    from lib.interactor.use_cases.upload_administration import UploadAdministration
    from thirdnews_contracts import CompletedUpload

    upload_id = uuid4()

    class Repository:
        async def lock_upload_intent(self, value):
            assert value == upload_id
            return SimpleNamespace(
                id=value,
                owner_id="owner",
                status="completed",
                final_key="objects/fixture",
                expected_size=7,
                sha256="a" * 64,
            )

    service = UploadAdministration(
        cast(Any, Repository()), None, max_bytes=50_000_000, presign_ttl_seconds=900
    )
    result = CompletedUpload.model_validate(await service.complete(upload_id, "owner"))
    assert result.size == 7 and result.sha256 == "a" * 64
