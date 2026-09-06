from __future__ import annotations

import uuid
from typing import Any

from lib.domain import NewsState
from lib.infra.storage.postgres.labels import SqlAlchemyLabelStorage
from lib.infra.storage.postgres.models import (
    Classifier,
    Facet,
    Job,
    News,
    NewsEffectiveLabel,
    NewsSourceLink,
    NewsVersion,
    OutboxEvent,
    Source,
    Submission,
)
from lib.interactor.errors import NotFoundError, ValidationError
from lib.interactor.interfaces.storage.news_admin import NewsAdminStorage
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .news_read_repository import NewsReadRepository
from .persistence_repository import PersistenceRepository


class SqlAlchemyNewsAdminRepository(NewsAdminStorage):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reader = NewsReadRepository(session)
        self.persistence = PersistenceRepository(session)

    async def stats(self) -> dict[str, Any]:
        rows = (
            await self.session.execute(select(News.status, func.count()).group_by(News.status))
        ).all()
        by_status = {str(status): int(count) for status, count in rows}
        pending_jobs = await self.session.scalar(
            select(func.count()).where(Job.status.in_(("pending", "running", "waiting_callback")))
        )
        sources = await self.session.scalar(select(func.count()).select_from(Source))
        classifiers = await self.session.scalar(
            select(func.count()).where(Classifier.enabled.is_(True))
        )
        return {
            "news_total": sum(by_status.values()),
            "by_status": by_status,
            "pending_jobs": int(pending_jobs or 0),
            "sources": int(sources or 0),
            "classifiers_active": int(classifiers or 0),
        }

    async def list_news(
        self,
        *,
        statuses: list[str] | None,
        query_text: str | None,
        gold: bool | None,
        source: str | None,
        unlabelled_facet: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        query = select(News).where(News.status != NewsState.DELETED)
        if statuses:
            query = query.where(News.status.in_(statuses))
        if query_text:
            query = query.join(NewsVersion, News.current_version_id == NewsVersion.id).where(
                (NewsVersion.title.ilike(f"%{query_text}%"))
                | (NewsVersion.body_md.ilike(f"%{query_text}%"))
            )
        if gold is not None:
            query = query.where(News.is_gold.is_(gold))
        if source:
            source_match = (
                select(NewsSourceLink.news_id)
                .join(Submission, Submission.id == NewsSourceLink.submission_id)
                .join(Source, Source.id == Submission.source_id)
                .where(
                    NewsSourceLink.news_id == News.id,
                    Source.slug == source,
                )
                .exists()
            )
            query = query.where(source_match)
        if unlabelled_facet:
            facet_exists = await self.session.scalar(
                select(Facet.id).where(
                    Facet.slug == unlabelled_facet,
                    Facet.enabled.is_(True),
                )
            )
            if facet_exists is None:
                raise ValidationError("unknown unlabelled facet")
            label_exists = (
                select(NewsEffectiveLabel.news_id)
                .join(Facet, Facet.id == NewsEffectiveLabel.facet_id)
                .where(
                    NewsEffectiveLabel.news_id == News.id,
                    Facet.slug == unlabelled_facet,
                )
                .exists()
            )
            query = query.where(~label_exists)
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = (
            await self.session.scalars(
                query.order_by(News.created_at.desc()).offset(offset).limit(limit)
            )
        ).all()
        return [await self.reader.serialize(row, admin=True) for row in rows], total

    async def news_for_submission(self, submission_id: uuid.UUID) -> dict[str, Any]:
        submission = await self.session.get(Submission, submission_id)
        if submission is None or submission.news_id is None:
            raise NotFoundError("news not found")
        return await self.news(submission.news_id)

    async def export_news(self, *, gold_only: bool) -> list[dict[str, Any]]:
        query = select(News).where(News.status != NewsState.DELETED)
        if gold_only:
            query = query.where(News.is_gold.is_(True))
        rows = (await self.session.scalars(query.order_by(News.created_at))).all()
        return [await self.reader.serialize(row, admin=True) for row in rows]

    async def set_gold(self, ids: list[uuid.UUID], is_gold: bool, actor: str) -> int:
        count = int(await self.session.scalar(select(func.count()).where(News.id.in_(ids))) or 0)
        await self.session.execute(update(News).where(News.id.in_(ids)).values(is_gold=is_gold))
        self.persistence.add_audit(
            actor=actor,
            action="gold",
            entity_type="news",
            entity_id="batch",
            payload={"ids": [str(value) for value in ids], "is_gold": is_gold},
        )
        await self.session.commit()
        return count

    async def news(self, news_id: uuid.UUID) -> dict[str, Any]:
        item = await self.session.get(News, news_id)
        if item is None or item.status == NewsState.DELETED:
            raise NotFoundError("news not found")
        return await self.reader.serialize(item, admin=True)

    async def manual_labels(
        self,
        news_id: uuid.UUID,
        *,
        labels: dict[str, list[str]],
        release_facets: list[str],
        user_id: uuid.UUID | None,
        actor: str,
    ) -> dict[str, Any]:
        news = await self.session.get(News, news_id, with_for_update=True)
        if news is None:
            raise NotFoundError("news not found")
        service = SqlAlchemyLabelStorage()
        try:
            await service.apply_manual(self.session, news, labels, release_facets, user_id)
            self.session.add(
                OutboxEvent(
                    topic="search.projection.requested.v2",
                    aggregate_id=news.id,
                    payload={
                        "news_id": str(news.id),
                        "revision": news.revision,
                        "status": str(news.status),
                    },
                )
            )
            self.persistence.add_audit(
                actor=actor,
                action="labels",
                entity_type="news",
                entity_id=news.id,
                payload={"labels": labels, "release_facets": release_facets},
            )
            await self.session.commit()
        except ValidationError:
            await self.session.rollback()
            raise
        return await self.reader.serialize(news, admin=True)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
