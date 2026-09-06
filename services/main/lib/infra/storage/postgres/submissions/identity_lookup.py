from __future__ import annotations

import uuid
from typing import Any

from lib.infra.storage.postgres.models import Source, Submission
from lib.interactor.errors import ConflictError
from lib.interactor.interfaces.storage.submission_identity import SubmissionIdentityStorage
from lib.interactor.interfaces.storage.unit_of_work import UnitOfWork
from sqlalchemy import or_, select


class SqlAlchemySubmissionIdentityStorage(SubmissionIdentityStorage):
    async def find(
        self, uow: UnitOfWork, identity: Any, bound_source_id: uuid.UUID | None
    ) -> Submission | None:
        conditions = []
        if identity.idempotency_key:
            conditions.append(Submission.idempotency_key == identity.idempotency_key)
        source_id = bound_source_id
        if identity.source:
            source_id = (
                await uow.session.execute(select(Source.id).where(Source.slug == identity.source))
            ).scalar_one_or_none()
        if source_id and identity.external_id:
            conditions.append(
                (Submission.source_id == source_id)
                & (Submission.external_id == identity.external_id)
            )
        if not conditions:
            return None
        rows = (
            (await uow.session.execute(select(Submission).where(or_(*conditions)))).scalars().all()
        )
        if len({row.id for row in rows}) > 1:
            raise ConflictError("submission identities refer to different existing submissions")
        return rows[0] if rows else None

    async def source(
        self, uow: UnitOfWork, slug: str | None, bound_source_id: uuid.UUID | None
    ) -> Source | None:
        if bound_source_id:
            source = await uow.session.get(Source, bound_source_id)
            if source is None or not source.enabled:
                raise ConflictError("the API key source is unavailable")
            if slug and source.slug != slug:
                raise ConflictError("the API key cannot submit for another source")
            return source
        if not slug:
            return None
        source = (
            await uow.session.execute(select(Source).where(Source.slug == slug))
        ).scalar_one_or_none()
        if source is None or not source.enabled:
            raise ConflictError("source is not registered or disabled")
        return source
