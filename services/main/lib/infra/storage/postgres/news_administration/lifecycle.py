from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lib.domain import NewsState
from lib.infra.storage.postgres.models import Job, News, NewsVersion
from lib.interactor.errors import ConflictError, ValidationError
from lib.interactor.interfaces.storage.news_lifecycle import NewsLifecycleStorage
from sqlalchemy import func, select

from .base import NewsAdministrationBase


class SqlAlchemyNewsLifecycleStorage(NewsAdministrationBase, NewsLifecycleStorage):
    async def edit(self, session: Any, news: News, changes: dict[str, Any], actor: str) -> News:
        allowed = {
            "title",
            "body_md",
            "source_link",
            "source_text",
            "language",
            "source_published_at",
            "extra",
        }
        unknown = changes.keys() - allowed
        if unknown:
            raise ValidationError(f"unsupported fields: {', '.join(sorted(unknown))}")
        current = await session.get(NewsVersion, news.current_version_id)
        values = {name: getattr(current, name) for name in allowed}
        values.update(changes)
        latest = await session.scalar(
            select(func.max(NewsVersion.number)).where(NewsVersion.news_id == news.id)
        )
        version = NewsVersion(news_id=news.id, number=(latest or 0) + 1, created_by=actor, **values)
        session.add(version)
        await session.flush()
        news.current_version_id = version.id
        news.revision += 1
        news.visibility_revision += 1
        if news.status == NewsState.PUBLISHED:
            await self.add_event(session, news, "search.projection.requested.v2")
        return news

    async def transition(self, session: Any, news: News, target: NewsState, actor: str) -> None:
        allowed = {
            NewsState.PUBLISHED: {
                NewsState.PENDING,
                NewsState.PROCESSING,
                NewsState.NEEDS_REVIEW,
                NewsState.REJECTED,
            },
            NewsState.REJECTED: {
                NewsState.PENDING,
                NewsState.PROCESSING,
                NewsState.NEEDS_REVIEW,
                NewsState.PUBLISHED,
            },
            NewsState.ARCHIVED: {NewsState.PUBLISHED, NewsState.REJECTED},
            NewsState.DELETED: set(NewsState) - {NewsState.DELETED},
        }
        if target not in allowed or NewsState(news.status) not in allowed[target]:
            raise ConflictError(f"cannot transition from {news.status} to {target}")
        news.status = target
        news.revision += 1
        news.visibility_revision += 1
        now = datetime.now(UTC)
        if target == NewsState.PUBLISHED:
            news.published_at = now
        elif target == NewsState.DELETED:
            news.deleted_at = now
        await self.add_event(session, news, "search.projection.requested.v2")
        self.add_audit(session, actor, target, news.id)

    async def reprocess(self, session: Any, news: News, actor: str) -> Job:
        job = Job(
            kind="pipeline",
            news_id=news.id,
            generation=news.revision + 1,
            max_attempts=self.max_attempts,
        )
        session.add(job)
        await session.flush()
        news.status = NewsState.PENDING
        news.current_attempt_id = None
        news.revision += 1
        news.visibility_revision += 1
        await self.add_event(session, news, "classification.requested.v2", {"job_id": str(job.id)})
        self.add_audit(session, actor, "reprocess", news.id)
        return job
