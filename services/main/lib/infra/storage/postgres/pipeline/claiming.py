from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lib.domain import ClaimedAttempt, PipelineRuntime
from lib.infra.storage.postgres.models import Job, News, ProcessingAttempt
from sqlalchemy import or_, select


class PipelineClaiming:
    async def claim(self, runtime: PipelineRuntime) -> ClaimedAttempt | None:
        now = datetime.now(UTC)
        async with runtime.sessions() as session, session.begin():
            job = await session.scalar(
                select(Job)
                .where(
                    Job.kind == "classification",
                    Job.status.in_(("pending", "running", "waiting_callback")),
                    Job.available_at <= now,
                    or_(
                        Job.status == "pending",
                        Job.lease_until.is_(None),
                        Job.lease_until < now,
                    ),
                )
                .order_by(Job.available_at, Job.created_at, Job.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            if job.current_attempt_id is not None:
                previous = await session.get(ProcessingAttempt, job.current_attempt_id)
                if previous is not None and previous.status in {"running", "waiting_callback"}:
                    previous.status = "timed_out"
                    previous.completed_at = now
                    previous.error_code = "deadline_exceeded"
                    previous.error_detail = "attempt lease or callback deadline expired"
            if job.attempt_count >= job.max_attempts:
                job.status = "dead_letter"
                job.completed_at = now
                job.owner = None
                job.lease_until = None
                return None
            job.generation += 1
            job.attempt_count += 1
            attempt = ProcessingAttempt(
                job_id=job.id,
                news_id=job.news_id,
                version_id=None,
                classifier_id=job.classifier_id,
                generation=job.generation,
                status="running",
                deadline_at=now + timedelta(seconds=runtime.callback_timeout),
            )
            session.add(attempt)
            await session.flush()
            if job.news_id is not None:
                news = await session.get(News, job.news_id)
                if news is not None:
                    attempt.version_id = news.current_version_id
            job.current_attempt_id = attempt.id
            job.status = "running"
            job.owner = runtime.node_id
            job.lease_until = now + timedelta(seconds=runtime.lease_seconds)
            job.last_error = None
            return ClaimedAttempt(job.id, attempt.id, job.generation)
