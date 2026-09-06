from __future__ import annotations

import uuid
from typing import Any

from lib.core.config import REMATERIALIZATION_JOB_KIND
from lib.domain import NewsState
from lib.infra.storage.postgres.models import (
    Attachment,
    Facet,
    FacetValue,
    Job,
    News,
    NewsEffectiveLabel,
    NewsSourceLink,
    SearchProjection,
    Setting,
    Source,
    Submission,
)
from lib.interactor.errors import NotFoundError
from lib.interactor.interfaces.storage.news_delivery import NewsDeliveryStorage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class SqlAlchemyNewsDeliveryRepository(NewsDeliveryStorage):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def news(self, news_id: uuid.UUID) -> News:
        item = await self.session.get(News, news_id)
        if item is None or item.deleted_at:
            raise NotFoundError("news not found")
        return item

    async def enforce_access(self, news: News, *, editor: bool, preset: dict[str, Any]) -> None:
        if not editor and news.status != NewsState.PUBLISHED:
            raise NotFoundError("news not found")
        if editor:
            return
        sources = preset.get("sources") or []
        if sources and not await self._source_match(news.id, sources):
            raise NotFoundError("news not found")
        for facet_slug, values in (preset.get("facets") or {}).items():
            if not await self._facet_match(news.id, facet_slug, values):
                raise NotFoundError("news not found")

    async def known_enabled_facets(self, slugs: set[str]) -> set[str]:
        return set(
            (
                await self.session.execute(
                    select(Facet.slug).where(Facet.slug.in_(slugs), Facet.enabled.is_(True))
                )
            ).scalars()
        )

    async def visibility_ready(self) -> bool:
        rematerializing = await self.session.scalar(
            select(Job.id)
            .where(
                Job.kind == REMATERIALIZATION_JOB_KIND,
                Job.status.in_(("pending", "running")),
            )
            .limit(1)
        )
        if rematerializing:
            return False
        stale = await self.session.scalar(
            select(func.count())
            .select_from(News)
            .outerjoin(SearchProjection, News.id == SearchProjection.news_id)
            .where(
                News.published_at.is_not(None),
                (SearchProjection.news_id.is_(None))
                | (SearchProjection.visibility_revision < News.visibility_revision)
                | (SearchProjection.status == "failed"),
            )
        )
        return not stale

    async def feed_rows(
        self, ids: list[uuid.UUID]
    ) -> tuple[dict[uuid.UUID, News], dict[uuid.UUID, SearchProjection]]:
        if not ids:
            return {}, {}
        rows = (
            await self.session.scalars(
                select(News).where(News.id.in_(ids), News.status == NewsState.PUBLISHED)
            )
        ).all()
        projections = (
            await self.session.scalars(
                select(SearchProjection).where(SearchProjection.news_id.in_(ids))
            )
        ).all()
        return {row.id: row for row in rows}, {row.news_id: row for row in projections}

    async def taxonomy(self) -> dict[str, Any]:
        facets = (
            (
                await self.session.execute(
                    select(Facet)
                    .options(selectinload(Facet.values))
                    .where(Facet.enabled.is_(True))
                    .order_by(Facet.position, Facet.slug)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        revision = await self.session.get(Setting, "taxonomy_revision")
        return {
            "version": str((revision.value or {}).get("revision") or 0) if revision else "0",
            "facets": [
                {
                    "id": str(item.id),
                    "slug": item.slug,
                    "title": item.title,
                    "description": item.description,
                    "type": item.kind,
                    "required": item.required,
                    "values": [
                        {
                            "id": str(value.id),
                            "slug": value.slug,
                            "title": value.title,
                            "description": value.description,
                        }
                        for value in item.values
                        if value.enabled
                    ],
                }
                for item in facets
            ],
        }

    async def recent_published(
        self, limit: int, *, editor: bool, preset: dict[str, Any]
    ) -> list[News]:
        query = select(News).where(News.status == NewsState.PUBLISHED)
        if not editor:
            sources = preset.get("sources") or []
            if sources:
                query = query.where(self._source_exists(News.id, sources))
            for facet_slug, values in (preset.get("facets") or {}).items():
                query = query.where(self._facet_exists(News.id, facet_slug, values))
        return list(
            (
                await self.session.scalars(query.order_by(News.published_at.desc()).limit(limit))
            ).all()
        )

    async def attachment_with_news(self, attachment_id: uuid.UUID) -> tuple[Attachment, News]:
        row = (
            await self.session.execute(
                select(Attachment, News)
                .join(News, News.id == Attachment.news_id)
                .where(
                    Attachment.id == attachment_id,
                    Attachment.active.is_(True),
                )
            )
        ).one_or_none()
        if row is None or not row.Attachment.object_key:
            raise NotFoundError("attachment not found")
        return row.Attachment, row.News

    async def _source_match(self, news_id: uuid.UUID, sources: list[str]) -> bool:
        return bool(await self.session.scalar(select(self._source_exists(news_id, sources))))

    async def _facet_match(self, news_id: uuid.UUID, facet_slug: str, values: list[str]) -> bool:
        return bool(
            await self.session.scalar(select(self._facet_exists(news_id, facet_slug, values)))
        )

    @staticmethod
    def _source_exists(news_id: Any, sources: list[str]):
        return (
            select(NewsSourceLink.news_id)
            .join(Submission, Submission.id == NewsSourceLink.submission_id)
            .join(Source, Source.id == Submission.source_id)
            .where(
                NewsSourceLink.news_id == news_id,
                Source.slug.in_(sources),
            )
            .exists()
        )

    @staticmethod
    def _facet_exists(news_id: Any, facet_slug: str, values: list[str]):
        return (
            select(NewsEffectiveLabel.news_id)
            .join(Facet, Facet.id == NewsEffectiveLabel.facet_id)
            .join(FacetValue, FacetValue.id == NewsEffectiveLabel.value_id)
            .where(
                NewsEffectiveLabel.news_id == news_id,
                Facet.slug == facet_slug,
                FacetValue.slug.in_(values),
            )
            .exists()
        )
