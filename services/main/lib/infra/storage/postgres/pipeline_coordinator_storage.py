from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from lib.infra.storage.postgres.models import (
    Attachment,
    Classifier,
    Facet,
    Job,
    News,
    NewsEffectiveLabel,
    NewsSourceLink,
    OutboxEvent,
    ProcessingAttempt,
    Setting,
    Source,
    Submission,
)
from lib.interactor.interfaces.storage.pipeline_coordinator import PipelineCoordinatorStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_OPEN = frozenset({"pending", "running", "waiting_callback", "waiting_children"})


class SqlAlchemyPipelineCoordinatorStorage(PipelineCoordinatorStorage):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        node_id: str,
        max_attempts: int,
        cooldown_seconds: int,
        lease_seconds: int,
        poll_seconds: float,
    ) -> None:
        self._sessions = session_factory
        self._node_id = node_id
        self._max_attempts = max_attempts
        self._cooldown = cooldown_seconds
        self._lease = lease_seconds
        self._poll = poll_seconds

    async def run(self, *, stop: asyncio.Event) -> None:
        while not stop.is_set():
            if await self.advance_one():
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._poll)
            except TimeoutError:
                pass

    async def advance_one(self) -> bool:
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            parent = await session.scalar(
                select(Job)
                .where(
                    Job.kind == "pipeline",
                    Job.status.in_(("pending", "running", "waiting_children")),
                    Job.available_at <= now,
                )
                .order_by(Job.available_at, Job.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if parent is None:
                return False
            if parent.status == "pending" or not parent.payload.get("stage"):
                await self._start(session, parent, now)
            else:
                await self._advance(session, parent, now)
        return True

    async def _start(self, session: AsyncSession, parent: Job, now: datetime) -> None:
        if parent.news_id is None:
            self._dead(parent, now, "pipeline job has no news")
            return
        news = await session.get(News, parent.news_id, with_for_update=True)
        if news is None or news.current_version_id is None:
            self._dead(parent, now, "pipeline news or version is missing")
            return
        parent.generation += 1
        parent.attempt_count += 1
        attempt = ProcessingAttempt(
            job_id=parent.id,
            news_id=news.id,
            version_id=news.current_version_id,
            generation=parent.generation,
            status="running",
            deadline_at=now + timedelta(seconds=max(self._lease, 24 * 60 * 60)),
            request_payload={"kind": "pipeline", "news_id": str(news.id)},
        )
        session.add(attempt)
        await session.flush()
        parent.current_attempt_id = attempt.id
        parent.owner = self._node_id
        news.current_attempt_id = attempt.id
        news.status = "processing"
        attachments = (
            await session.scalars(
                select(Attachment).where(
                    Attachment.news_id == news.id,
                    Attachment.active.is_(True),
                    Attachment.object_key.is_(None),
                    Attachment.original_url.is_not(None),
                )
            )
        ).all()
        children: list[str] = []
        for attachment in attachments:
            child = Job(
                kind="attachment",
                news_id=news.id,
                submission_id=attachment.submission_id,
                max_attempts=self._max_attempts,
                payload={
                    "attachment_id": str(attachment.id),
                    "pipeline_attempt_id": str(attempt.id),
                },
            )
            session.add(child)
            await session.flush()
            children.append(str(child.id))
        parent.payload = {
            "stage": "attachments",
            "children": children,
            "pipeline_attempt_id": str(attempt.id),
        }
        parent.status = "waiting_children"
        parent.available_at = now + timedelta(seconds=self._cooldown)
        parent.lease_until = None
        parent.owner = None

    async def _advance(self, session: AsyncSession, parent: Job, now: datetime) -> None:
        try:
            child_ids = [uuid.UUID(value) for value in parent.payload.get("children", [])]
        except TypeError, ValueError:
            self._dead(parent, now, "pipeline child list is invalid")
            return
        children = (
            (await session.scalars(select(Job).where(Job.id.in_(child_ids)))).all()
            if child_ids
            else []
        )
        if any(child.status in _OPEN for child in children):
            parent.available_at = now + timedelta(seconds=self._cooldown)
            return
        if parent.payload.get("stage") == "attachments":
            if any(child.status != "succeeded" for child in children):
                await self._finish(session, parent, children, now)
                return
            await self._start_classifiers(session, parent, now)
            return
        await self._finish(session, parent, children, now)

    async def _start_classifiers(self, session: AsyncSession, parent: Job, now: datetime) -> None:
        if parent.news_id is None:
            self._dead(parent, now, "pipeline news is missing")
            return
        private_source = await session.scalar(
            select(Source.id)
            .join(Submission, Submission.source_id == Source.id)
            .join(NewsSourceLink, NewsSourceLink.submission_id == Submission.id)
            .where(NewsSourceLink.news_id == parent.news_id, Source.skip_classification.is_(True))
            .limit(1)
        )
        if private_source is not None:
            await self._finish(session, parent, [], now)
            return
        classifiers = (
            await session.scalars(
                select(Classifier).where(Classifier.enabled.is_(True)).order_by(Classifier.priority)
            )
        ).all()
        children: list[str] = []
        for classifier in classifiers:
            child = Job(
                kind="classification",
                news_id=parent.news_id,
                classifier_id=classifier.id,
                max_attempts=self._max_attempts,
                payload={
                    "parent_job_id": str(parent.id),
                    "pipeline_attempt_id": parent.payload["pipeline_attempt_id"],
                },
            )
            session.add(child)
            await session.flush()
            children.append(str(child.id))
        parent.payload = {
            **parent.payload,
            "stage": "classification",
            "children": children,
        }
        parent.available_at = now + timedelta(seconds=self._cooldown)

    async def _finish(
        self, session: AsyncSession, parent: Job, children: Sequence[Job], now: datetime
    ) -> None:
        news = await session.get(News, parent.news_id, with_for_update=True)
        attempt = await session.get(
            ProcessingAttempt, parent.current_attempt_id, with_for_update=True
        )
        if news is None or attempt is None or news.current_attempt_id != attempt.id:
            parent.status = "cancelled"
            parent.completed_at = now
            return
        failed = [child for child in children if child.status != "succeeded"]
        can_publish = not failed and await self._auto_publish_allowed(session, news)
        news.status = "published" if can_publish else "needs_review"
        if can_publish:
            news.published_at = now
        news.current_attempt_id = None
        news.revision += 1
        news.visibility_revision += 1
        attempt.status = "succeeded" if not failed else "completed_with_errors"
        attempt.completed_at = now
        attempt.validated_result = {
            "children": [str(child.id) for child in children],
            "failed": [str(child.id) for child in failed],
            "published": can_publish,
        }
        parent.status = "succeeded"
        parent.result = dict(attempt.validated_result)
        parent.completed_at = now
        parent.owner = None
        parent.lease_until = None
        session.add(
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

    @staticmethod
    async def _auto_publish_allowed(session: AsyncSession, news: News) -> bool:
        setting = await session.get(Setting, "auto_publish")
        if setting is None or setting.value.get("enabled") is not True:
            return False
        required = (
            await session.scalars(
                select(Facet.id).where(Facet.enabled.is_(True), Facet.required.is_(True))
            )
        ).all()
        if not required:
            return True
        labeled = set(
            (
                await session.scalars(
                    select(NewsEffectiveLabel.facet_id).where(
                        NewsEffectiveLabel.news_id == news.id,
                        NewsEffectiveLabel.facet_id.in_(required),
                    )
                )
            ).all()
        )
        return set(required) <= labeled

    @staticmethod
    def _dead(parent: Job, now: datetime, reason: str) -> None:
        parent.status = "dead_letter"
        parent.last_error = reason
        parent.completed_at = now
