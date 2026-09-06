from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from lib.core.config import SEARCH_FILTERABLE, SEARCH_SORTABLE
from lib.dto.projection_work import ProjectionWork
from lib.infra.storage.postgres.models import (
    Attachment,
    Facet,
    FacetValue,
    News,
    NewsEffectiveLabel,
    NewsSourceLink,
    NewsVersion,
    SearchProjection,
    Source,
    Submission,
)
from lib.interactor.errors.search_not_ready import SearchNotReady
from lib.interactor.errors.search_task_failed import SearchTaskFailed
from lib.interactor.interfaces.clients.search_projection import SearchProjectionClient
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .client import MeiliSearchClient


class SearchIndexer(SearchProjectionClient):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        client: MeiliSearchClient,
        *,
        owner: str,
        poll_seconds: float = 0.5,
        lease_seconds: int = 120,
    ) -> None:
        self._sessions = session_factory
        self._client = client
        self._owner = owner
        self._poll_seconds = poll_seconds
        self._lease_seconds = lease_seconds
        self._index_lock = int.from_bytes(
            hashlib.blake2b(client.index.encode(), digest_size=8).digest(), signed=True
        )

    async def run(self, *, stop: asyncio.Event) -> None:
        await self._client.ensure_index()
        await self._client.configure(
            filterable=SEARCH_FILTERABLE,
            sortable=SEARCH_SORTABLE,
        )
        while not stop.is_set():
            if await self.process_one():
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._poll_seconds)
            except TimeoutError:
                pass

    async def process_one(self) -> bool:

        async with self._sessions() as guard, guard.begin():
            acquired = await guard.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": self._index_lock}
            )
            if not acquired:
                return False
            return await self.process_claimed()

    async def process_claimed(self) -> bool:
        work = await self._claim_one()
        if work is None:
            return False
        try:
            document = await self._document(work.news_id)
            if work.existing_task_uid is not None:
                task_uid = work.existing_task_uid
            elif document is None:
                task_uid = await self._client.delete_documents([str(work.news_id)])
                await self._store_task(work, task_uid)
            else:
                task_uid = await self._client.put_documents([document])
                await self._store_task(work, task_uid)
            await self._client.wait_task(task_uid)
            await self._complete(work, task_uid)
        except Exception as exc:
            await self._fail(work, exc)
        return True

    async def assert_visibility_ready(self) -> None:

        async with self._sessions() as session:
            pending = await session.scalar(
                select(News.id)
                .outerjoin(SearchProjection, SearchProjection.news_id == News.id)
                .where(
                    or_(News.status == "published", News.visibility_revision > 1),
                    or_(
                        SearchProjection.news_id.is_(None),
                        SearchProjection.visibility_revision < News.visibility_revision,
                        SearchProjection.status == "failed",
                    ),
                )
                .limit(1)
            )
        if pending is not None:
            raise SearchNotReady("visibility projection is not current")

    async def reindex_all(self, *, page_size: int = 500) -> int:
        async with self._sessions() as guard, guard.begin():
            await guard.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": self._index_lock}
            )
            return await self.rebuild_snapshot(page_size=page_size)

    async def rebuild_snapshot(self, *, page_size: int) -> int:
        snapshots: dict[uuid.UUID, tuple[int, int]] = {}

        async with self._sessions() as session, session.begin():
            await session.execute(
                update(SearchProjection).values(
                    indexed_revision=0, visibility_revision=0, status="pending", task_uid=None
                )
            )
        count = await self._client.replace_all(
            self.stream_snapshot(snapshots, page_size=page_size),
            batch_size=page_size,
            filterable=SEARCH_FILTERABLE,
            sortable=SEARCH_SORTABLE,
        )
        async with self._sessions() as session, session.begin():
            for news_id, (revision, visibility) in snapshots.items():
                projection = await session.get(SearchProjection, news_id, with_for_update=True)
                news = await session.get(News, news_id)
                if news is None:
                    continue
                if projection is None:
                    projection = SearchProjection(news_id=news_id, desired_revision=news.revision)
                    session.add(projection)
                projection.indexed_revision = revision
                projection.visibility_revision = visibility
                projection.desired_revision = max(projection.desired_revision, news.revision)
                projection.status = (
                    "ready"
                    if (news.revision, news.visibility_revision) == (revision, visibility)
                    else "pending"
                )
                projection.task_uid = None
                projection.error = None
                projection.updated_at = datetime.now(UTC)
        return count

    async def stream_snapshot(
        self, snapshots: dict[uuid.UUID, tuple[int, int]], *, page_size: int
    ) -> AsyncIterator[dict[str, Any]]:
        last_id: uuid.UUID | None = None
        while True:
            async with self._sessions() as session:
                statement = (
                    select(News.id, News.revision, News.visibility_revision)
                    .order_by(News.id)
                    .limit(page_size)
                )
                if last_id is not None:
                    statement = statement.where(News.id > last_id)
                rows = (await session.execute(statement)).all()
            if not rows:
                break
            for news_id, revision, visibility in rows:
                document = await self._document(news_id)
                if document is not None:
                    snapshots[news_id] = (document["revision"], document["visibility_revision"])
                    yield document
                else:
                    snapshots[news_id] = (revision, visibility)
            last_id = rows[-1][0]

    async def _claim_one(self) -> ProjectionWork | None:
        async with self._sessions() as session, session.begin():
            projection = await session.scalar(
                select(SearchProjection)
                .where(
                    SearchProjection.desired_revision > SearchProjection.indexed_revision,
                    SearchProjection.status.in_(("pending", "failed", "indexing")),
                    or_(
                        SearchProjection.status == "pending",
                        SearchProjection.updated_at
                        <= datetime.now(UTC) - timedelta(seconds=self._lease_seconds),
                    ),
                )
                .order_by(SearchProjection.updated_at, SearchProjection.news_id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if projection is None:
                return None
            projection.status = "indexing"
            projection.updated_at = datetime.now(UTC)
            return ProjectionWork(
                projection.news_id,
                projection.desired_revision,
                projection.visibility_revision,
                projection.task_uid,
            )

    async def _store_task(self, work: ProjectionWork, task_uid: int) -> None:
        async with self._sessions() as session, session.begin():
            projection = await session.get(SearchProjection, work.news_id, with_for_update=True)
            if projection is None:
                return
            if projection.desired_revision == work.revision:
                projection.task_uid = task_uid
                projection.updated_at = datetime.now(UTC)

    async def _complete(self, work: ProjectionWork, task_uid: int) -> None:
        async with self._sessions() as session, session.begin():
            projection = await session.get(SearchProjection, work.news_id, with_for_update=True)
            news = await session.get(News, work.news_id)
            if projection is None or news is None:
                return
            if projection.desired_revision != work.revision or news.revision != work.revision:
                projection.desired_revision = max(projection.desired_revision, news.revision)
                projection.status = "pending"
                projection.task_uid = None
                return
            projection.indexed_revision = work.revision
            projection.visibility_revision = news.visibility_revision
            projection.status = "ready"
            projection.task_uid = None
            projection.error = None
            projection.updated_at = datetime.now(UTC)

    async def _fail(self, work: ProjectionWork, error: Exception) -> None:
        async with self._sessions() as session, session.begin():
            projection = await session.get(SearchProjection, work.news_id, with_for_update=True)
            if projection is None:
                return
            projection.status = "failed"
            projection.error = type(error).__name__
            if isinstance(error, SearchTaskFailed):
                projection.task_uid = None
            projection.updated_at = datetime.now(UTC)

    async def _document(self, news_id: uuid.UUID) -> dict[str, Any] | None:
        async with self._sessions() as session:
            news = await session.get(News, news_id)
            if news is None or news.status != "published" or news.deleted_at is not None:
                return None
            version = await session.get(NewsVersion, news.current_version_id)
            if version is None:
                return None
            rows = (
                await session.execute(
                    select(Facet.slug, FacetValue.slug)
                    .join(NewsEffectiveLabel, NewsEffectiveLabel.facet_id == Facet.id)
                    .join(FacetValue, FacetValue.id == NewsEffectiveLabel.value_id)
                    .where(
                        NewsEffectiveLabel.news_id == news.id,
                        Facet.enabled.is_(True),
                        FacetValue.enabled.is_(True),
                    )
                )
            ).all()
            facets: dict[str, list[str]] = {}
            for axis, value in rows:
                facets.setdefault(axis, []).append(value)
            sources = (
                await session.execute(
                    select(Source.slug, Source.id)
                    .join(Submission, Submission.source_id == Source.id)
                    .join(NewsSourceLink, NewsSourceLink.submission_id == Submission.id)
                    .where(NewsSourceLink.news_id == news.id)
                    .distinct()
                    .order_by(Source.slug)
                )
            ).all()
            attachment_id = await session.scalar(
                select(Attachment.id)
                .where(
                    Attachment.news_id == news.id,
                    Attachment.active.is_(True),
                    Attachment.status == "stored",
                    Attachment.object_key.is_not(None),
                )
                .limit(1)
            )
            received_at = await session.scalar(
                select(func.min(Submission.received_at))
                .join(NewsSourceLink, NewsSourceLink.submission_id == Submission.id)
                .where(NewsSourceLink.news_id == news.id)
            )
            publication_date = (
                version.source_published_at or news.published_at or received_at or news.created_at
            )
            return {
                "id": str(news.id),
                "title": version.title,
                "body": version.body_md,
                "source_link": version.source_link,
                "source_text": version.source_text,
                "source": [slug for slug, _ in sources],
                "source_ids": [str(source_id) for _, source_id in sources],
                "has_attachments": attachment_id is not None,
                "published_at_ts": publication_date.timestamp(),
                "received_at_ts": (received_at or news.created_at).timestamp(),
                "language": version.language,
                "published_at": publication_date.isoformat(),
                "status": news.status,
                "urgency": news.urgency,
                "impact": news.impact,
                "editorial_priority": news.editorial_priority,
                "importance": news.importance,
                "facets": facets,
                "revision": news.revision,
                "visibility_revision": news.visibility_revision,
            }
