from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from lib.core.config import REMATERIALIZATION_BATCH_SIZE, REMATERIALIZATION_JOB_KIND
from lib.infra.storage.postgres.labels import SqlAlchemyLabelStorage
from lib.infra.storage.postgres.models import Job, ManualLabelDecision, News, NewsLabel
from lib.infra.storage.postgres.repositories.persistence_repository import PersistenceRepository
from lib.interactor.interfaces.storage.rematerialization import RematerializationStorage
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyRematerializationStorage(RematerializationStorage):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        node_id: str,
        lease_seconds: int,
        cooldown_seconds: int,
        batch_size: int = REMATERIALIZATION_BATCH_SIZE,
    ) -> None:
        self._sessions = session_factory
        self._node_id = node_id
        self._lease_seconds = lease_seconds
        self._cooldown_seconds = cooldown_seconds
        self._batch_size = batch_size

    async def process_one(self) -> bool:
        job_id = await self._claim_one()
        if job_id is None:
            return False
        try:
            await self._process_chunk(job_id)
        except Exception as error:
            await self._retry(job_id, error)
        return True

    async def _claim_one(self) -> uuid.UUID | None:
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            job = await session.scalar(
                select(Job)
                .where(
                    Job.kind == REMATERIALIZATION_JOB_KIND,
                    Job.available_at <= now,
                    or_(
                        Job.status == "pending",
                        (Job.status == "running") & (Job.lease_until < now),
                    ),
                )
                .order_by(Job.available_at, Job.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            job.status = "running"
            job.owner = self._node_id
            job.lease_until = now + timedelta(seconds=self._lease_seconds)
            job.attempt_count += 1
            return job.id

    async def _process_chunk(self, job_id: uuid.UUID) -> None:
        async with self._sessions() as session, session.begin():
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None or job.status != "running" or job.owner != self._node_id:
                return
            news_ids = await self._news_ids(session, job.payload)
            if not news_ids:
                job.status = "succeeded"
                job.completed_at = datetime.now(UTC)
                job.owner = None
                job.lease_until = None
                return
            labels = SqlAlchemyLabelStorage()
            persistence = PersistenceRepository(session)
            for news_id in news_ids:
                news = await session.get(News, news_id, with_for_update=True)
                if news is None or news.status == "deleted":
                    continue
                await labels.recompute(session, news)
                persistence.enqueue_news_projection(news)
            job.payload = {**job.payload, "cursor": str(news_ids[-1])}
            job.status = "pending"
            job.available_at = datetime.now(UTC)
            job.owner = None
            job.lease_until = None

    async def _news_ids(self, session: AsyncSession, payload: dict) -> list[uuid.UUID]:
        cursor = payload.get("cursor")
        query = select(News.id).where(News.status != "deleted")
        if cursor:
            query = query.where(News.id > uuid.UUID(str(cursor)))
        scope = str(payload.get("scope") or "all")
        scope_id = payload.get("scope_id")
        if scope == "classifier":
            prefix = f"{scope_id}:"
            query = query.where(
                exists(
                    select(NewsLabel.id).where(
                        NewsLabel.news_id == News.id,
                        NewsLabel.origin.in_(("classifier", "shadow")),
                        NewsLabel.origin_key.startswith(prefix, autoescape=True),
                    )
                )
            )
        elif scope == "facet":
            query = query.where(
                or_(
                    exists(
                        select(NewsLabel.id).where(
                            NewsLabel.news_id == News.id,
                            NewsLabel.facet_id == uuid.UUID(str(scope_id)),
                        )
                    ),
                    exists(
                        select(ManualLabelDecision.id).where(
                            ManualLabelDecision.news_id == News.id,
                            ManualLabelDecision.facet_id == uuid.UUID(str(scope_id)),
                        )
                    ),
                )
            )
        elif scope == "value":
            query = query.where(
                exists(
                    select(NewsLabel.id).where(
                        NewsLabel.news_id == News.id,
                        NewsLabel.value_id == uuid.UUID(str(scope_id)),
                    )
                )
            )
        elif scope != "all":
            raise ValueError("unknown rematerialization scope")
        return list(await session.scalars(query.order_by(News.id).limit(self._batch_size)))

    async def _retry(self, job_id: uuid.UUID, error: Exception) -> None:
        async with self._sessions() as session, session.begin():
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None or job.status != "running" or job.owner != self._node_id:
                return
            job.status = "pending"
            job.available_at = datetime.now(UTC) + timedelta(seconds=self._cooldown_seconds)
            job.owner = None
            job.lease_until = None
            job.last_error = type(error).__name__
