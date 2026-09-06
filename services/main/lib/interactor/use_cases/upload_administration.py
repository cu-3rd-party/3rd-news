from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from lib.interactor.errors import ConflictError, NotFoundError, ValidationError
from lib.interactor.interfaces.storage.ingest_repository import IngestRepository


class UploadAdministration:
    def __init__(
        self,
        repository: IngestRepository,
        storage: Any,
        *,
        max_bytes: int,
        presign_ttl_seconds: int,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.max_bytes = max_bytes
        self.presign_ttl_seconds = presign_ttl_seconds

    async def presign(
        self, *, owner_id: str, size: int, content_type: str, sha256: str | None
    ) -> dict[str, Any]:
        if size > self.max_bytes:
            raise ValidationError("file is too large")
        intent = await self.repository.create_upload_intent(
            owner_id=owner_id,
            temporary_key=f"pending/{owner_id}/{uuid.uuid4()}",
            expected_size=size,
            content_type=content_type,
            sha256=sha256,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.presign_ttl_seconds),
        )
        upload = await self.storage.create_upload(
            owner_id=owner_id,
            intent_id=str(intent.id),
            size=size,
            content_type=content_type,
            sha256=sha256,
        )
        intent.temp_key = upload.key
        await self.repository.commit()
        return {
            "upload_id": str(intent.id),
            "url": upload.url,
            "method": "PUT",
            "headers": upload.headers,
            "expires_at": intent.expires_at,
        }

    async def complete(self, upload_id: uuid.UUID, owner_id: str) -> dict[str, Any]:
        intent = await self.repository.lock_upload_intent(upload_id)
        if intent is None or intent.owner_id != owner_id:
            raise NotFoundError("upload not found")
        if intent.status == "completed":
            return {
                "upload_id": str(intent.id),
                "status": intent.status,
                "object_key": intent.final_key,
                "size": intent.expected_size,
                "sha256": intent.sha256,
            }
        if intent.expires_at <= datetime.now(UTC):
            raise ConflictError("upload expired")
        if not intent.sha256:
            raise ConflictError("upload intent has no expected digest")
        completed = await self.storage.complete_upload(
            temporary_key=intent.temp_key,
            owner_id=owner_id,
            intent_id=str(intent.id),
            expected_size=intent.expected_size,
            expected_content_type=intent.content_type,
            expected_sha256=intent.sha256,
        )
        intent.final_key = completed.key
        intent.sha256 = completed.sha256
        intent.status = "completed"
        intent.completed_at = datetime.now(UTC)
        await self.repository.commit()
        return {
            "upload_id": str(intent.id),
            "status": intent.status,
            "object_key": intent.final_key,
            "size": completed.size,
            "sha256": completed.sha256,
        }
