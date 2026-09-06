from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from lib.dto.attachmentclaim import AttachmentClaim
from lib.infra.clients.http import SafeFetcher
from lib.infra.storage.postgres.models import Attachment, Job, News, ProcessingAttempt
from lib.infra.storage.s3 import S3ObjectStore, extract_text_isolated
from lib.interactor.interfaces.storage.attachmentprocessing import AttachmentProcessingStorage
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyAttachmentProcessingStorage(AttachmentProcessingStorage):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        fetcher: SafeFetcher,
        storage: S3ObjectStore,
        *,
        node_id: str,
        lease_seconds: int = 120,
        poll_seconds: float = 0.5,
        cooldown_seconds: int = 5,
    ) -> None:
        self._sessions = session_factory
        self._fetcher = fetcher
        self._storage = storage
        self._node_id = node_id
        self._lease_seconds = lease_seconds
        self._poll_seconds = poll_seconds
        self._cooldown = cooldown_seconds

    async def run(self, *, stop: asyncio.Event, concurrency: int = 2) -> None:
        async with asyncio.TaskGroup() as group:
            for _ in range(concurrency):
                group.create_task(self.run_slot(stop))

    async def run_slot(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            claim = await self.claim()
            if claim is None:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self._poll_seconds)
                except TimeoutError:
                    pass
                continue
            await self.process(claim)

    async def claim(self) -> AttachmentClaim | None:
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            job = await session.scalar(
                select(Job)
                .where(
                    Job.kind == "attachment",
                    Job.status.in_(("pending", "running")),
                    Job.available_at <= now,
                    or_(Job.status == "pending", Job.lease_until.is_(None), Job.lease_until < now),
                )
                .order_by(Job.available_at, Job.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            if job.attempt_count >= job.max_attempts:
                job.status = "dead_letter"
                job.completed_at = now
                return None
            try:
                attachment_id = uuid.UUID(str(job.payload["attachment_id"]))
            except KeyError, ValueError, TypeError:
                job.status = "dead_letter"
                job.last_error = "attachment job has no valid attachment_id"
                job.completed_at = now
                return None
            previous = (
                await session.get(ProcessingAttempt, job.current_attempt_id)
                if job.current_attempt_id
                else None
            )
            if previous is not None and previous.status == "running":
                previous.status = "timed_out"
                previous.completed_at = now
                previous.error_code = "lease_expired"
            job.generation += 1
            job.attempt_count += 1
            attempt = ProcessingAttempt(
                job_id=job.id,
                news_id=job.news_id,
                version_id=None,
                classifier_id=None,
                generation=job.generation,
                status="running",
                request_payload={"attachment_id": str(attachment_id)},
                deadline_at=now + timedelta(seconds=self._lease_seconds),
            )
            if job.news_id:
                news = await session.get(News, job.news_id)
                attempt.version_id = news.current_version_id if news else None
            session.add(attempt)
            await session.flush()
            job.current_attempt_id = attempt.id
            job.status = "running"
            job.owner = self._node_id
            job.lease_until = attempt.deadline_at
            return AttachmentClaim(job.id, attempt.id, job.generation, attachment_id)

    async def process(self, claim: AttachmentClaim) -> None:
        try:
            async with self._sessions() as session:
                attachment = await session.get(Attachment, claim.attachment_id)
                if attachment is None or not attachment.original_url:
                    raise ValueError("attachment URL is missing")
                source_url = attachment.original_url
                filename = attachment.filename
                expected_type = attachment.content_type
                owner_id = str(attachment.news_id or attachment.submission_id or "system")
            fetched = await self._fetcher.fetch_bytes(source_url)
            content_type = fetched.content_type or expected_type or "application/octet-stream"
            stored = await self._storage.put_bytes(
                fetched.body,
                content_type=content_type,
                owner_id=owner_id,
                source_id=str(claim.attachment_id),
            )
            extracted = await extract_text_isolated(
                fetched.body,
                content_type=content_type,
                filename=filename,
            )
            async with self._sessions() as session, session.begin():
                job = await session.get(Job, claim.job_id, with_for_update=True)
                attempt = await session.get(
                    ProcessingAttempt, claim.attempt_id, with_for_update=True
                )
                attachment = await session.get(
                    Attachment, claim.attachment_id, with_for_update=True
                )
                if (
                    job is None
                    or not self.matches(job, claim)
                    or attempt is None
                    or attachment is None
                ):
                    return
                pipeline_attempt = job.payload.get("pipeline_attempt_id")
                if pipeline_attempt is not None and job.news_id is not None:
                    news = await session.get(News, job.news_id)
                    if news is None or str(news.current_attempt_id) != str(pipeline_attempt):
                        return
                attachment.object_key = stored.key
                attachment.size = stored.size
                attachment.sha256 = stored.sha256
                attachment.content_type = stored.content_type
                attachment.extracted_text = extracted
                attachment.status = "stored"
                attachment.error = None
                attempt.status = "succeeded"
                attempt.completed_at = datetime.now(UTC)
                attempt.validated_result = {
                    "attachment_id": str(attachment.id),
                    "size": stored.size,
                    "sha256": stored.sha256,
                    "content_type": stored.content_type,
                    "text_extracted": extracted is not None,
                }
                job.status = "succeeded"
                job.result = dict(attempt.validated_result)
                job.completed_at = attempt.completed_at
                job.owner = None
                job.lease_until = None
        except Exception as exc:
            await self.fail(claim, exc)

    async def fail(self, claim: AttachmentClaim, error: Exception) -> None:
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            job = await session.get(Job, claim.job_id, with_for_update=True)
            attempt = await session.get(ProcessingAttempt, claim.attempt_id, with_for_update=True)
            attachment = await session.get(Attachment, claim.attachment_id, with_for_update=True)
            if job is None or not self.matches(job, claim) or attempt is None:
                return

            detail = type(error).__name__
            attempt.status = "failed"
            attempt.completed_at = now
            attempt.error_code = detail
            attempt.error_detail = detail
            job.last_error = detail
            job.owner = None
            job.lease_until = None
            if attachment is not None:
                attachment.status = "failed"
                attachment.error = detail
            if job.attempt_count >= job.max_attempts:
                job.status = "dead_letter"
                job.completed_at = now
            else:
                job.status = "pending"
                job.available_at = now + timedelta(
                    seconds=self._cooldown * 2 ** min(max(job.attempt_count - 1, 0), 8)
                )

    @staticmethod
    def matches(job: Job | None, claim: AttachmentClaim) -> bool:
        return bool(
            job is not None
            and job.current_attempt_id == claim.attempt_id
            and job.generation == claim.generation
        )
