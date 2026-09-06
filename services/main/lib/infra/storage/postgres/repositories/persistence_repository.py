from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lib.core.config import REMATERIALIZATION_JOB_KIND
from lib.infra.storage.postgres.models import AuditLog, Job, News, OutboxEvent
from lib.interactor.interfaces.storage.persistence import PersistenceStorage
from sqlalchemy.ext.asyncio import AsyncSession


class PersistenceRepository(PersistenceStorage):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_audit(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: object,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor=actor,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id),
                payload=payload or {},
            )
        )

    async def request_news_projections(self, news_ids: Iterable[UUID]) -> None:
        for news_id in set(news_ids):
            news = await self.session.get(News, news_id, with_for_update=True)
            if news is None:
                continue
            news.revision += 1
            news.visibility_revision += 1
            self.enqueue_news_projection(news)

    def enqueue_news_projection(self, news: News) -> None:
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

    def enqueue_rematerialization(self, *, scope: str, scope_id: object | None = None) -> Job:
        payload: dict[str, Any] = {"scope": scope}
        if scope_id is not None:
            payload["scope_id"] = str(scope_id)
        job = Job(
            kind=REMATERIALIZATION_JOB_KIND,
            status="pending",
            available_at=datetime.now(UTC),
            payload=payload,
            max_attempts=0,
        )
        self.session.add(job)
        return job
