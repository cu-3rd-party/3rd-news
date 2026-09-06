from __future__ import annotations

import uuid
from datetime import UTC, datetime

from lib.core.config import UPLOAD_PENDING_MAX_BYTES, UPLOAD_PENDING_MAX_COUNT
from lib.infra.storage.postgres.models import Submission, UploadIntent
from lib.interactor.errors import ConflictError
from lib.interactor.interfaces.storage.ingest_repository import IngestRepository
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyIngestRepository(IngestRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def submission(self, submission_id: uuid.UUID) -> Submission | None:
        return await self.session.get(Submission, submission_id)

    async def create_upload_intent(
        self,
        *,
        owner_id: str,
        temporary_key: str,
        expected_size: int,
        content_type: str,
        sha256: str | None,
        expires_at: datetime,
    ) -> UploadIntent:

        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(owner_id, 17)))
        )
        count, reserved = (
            await self.session.execute(
                select(
                    func.count(UploadIntent.id),
                    func.coalesce(func.sum(UploadIntent.expected_size), 0),
                ).where(
                    UploadIntent.owner_id == owner_id,
                    UploadIntent.attachment_id.is_(None),
                    or_(
                        UploadIntent.status == "completed",
                        (UploadIntent.status == "pending")
                        & (UploadIntent.expires_at > datetime.now(UTC)),
                    ),
                )
            )
        ).one()
        if count >= UPLOAD_PENDING_MAX_COUNT or reserved + expected_size > UPLOAD_PENDING_MAX_BYTES:
            raise ConflictError("unfinished upload quota exceeded")
        intent = UploadIntent(
            owner_id=owner_id,
            temp_key=temporary_key,
            expected_size=expected_size,
            content_type=content_type,
            sha256=sha256,
            expires_at=expires_at,
        )
        self.session.add(intent)
        await self.session.flush()
        return intent

    async def lock_upload_intent(self, upload_id: uuid.UUID) -> UploadIntent | None:
        return (
            await self.session.execute(
                select(UploadIntent).where(UploadIntent.id == upload_id).with_for_update()
            )
        ).scalar_one_or_none()

    async def commit(self) -> None:
        await self.session.commit()
