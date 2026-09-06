from __future__ import annotations

import uuid
from typing import Any

from lib.infra.storage.postgres.models import NewsSourceLink, Source, Submission
from lib.interactor.errors import ConflictError, NotFoundError
from lib.interactor.interfaces.storage.source import SourceStorage
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .catalog_repository_base import CatalogRepositoryBase


class SourceRepository(CatalogRepositoryBase, SourceStorage):
    async def list_sources(self) -> list[dict[str, Any]]:
        rows = (await self.session.scalars(select(Source).order_by(Source.title))).all()
        return [self.source_values(item) for item in rows]

    async def create_source(self, values: dict[str, Any], actor: str) -> dict[str, Any]:
        item = Source(**values)
        self.session.add(item)
        try:
            await self.session.flush()
            self.persistence.add_audit(
                actor=actor, action="create", entity_type="source", entity_id=item.id
            )
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("source already exists") from error
        return self.source_values(item)

    async def update_source(
        self, source_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        item = await self.session.get(Source, source_id, with_for_update=True)
        if item is None:
            raise NotFoundError("source not found")
        affected = (
            await self.session.scalars(
                select(NewsSourceLink.news_id)
                .join(Submission, Submission.id == NewsSourceLink.submission_id)
                .where(Submission.source_id == source_id)
            )
        ).all()
        for key, value in values.items():
            setattr(item, key, value)
        await self.persistence.request_news_projections(affected)
        self.persistence.add_audit(
            actor=actor, action="update", entity_type="source", entity_id=item.id
        )
        await self.session.commit()
        return self.source_values(item)

    @staticmethod
    def source_values(item: Source) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "slug": item.slug,
            "title": item.title,
            "kind": item.kind,
            "url": item.url,
            "description": item.description,
            "enabled": item.enabled,
            "skip_classification": item.skip_classification,
            "default_labels": item.default_labels,
        }
