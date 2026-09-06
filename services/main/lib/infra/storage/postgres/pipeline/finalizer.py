from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lib.domain import ClaimedAttempt, PipelineRuntime
from lib.infra.storage.postgres.models import Job, ProcessingAttempt
from lib.interactor.errors import ClassifierProtocolError, StaleAttemptError

from .fence import PipelineFence


class PipelineFinalizer:
    async def mark_waiting(
        self, runtime: PipelineRuntime, claimed: ClaimedAttempt, raw_body: bytes
    ) -> None:
        async with runtime.sessions() as session, session.begin():
            job = await session.get(Job, claimed.job_id, with_for_update=True)
            attempt = await session.get(ProcessingAttempt, claimed.attempt_id, with_for_update=True)
            if job is None or not PipelineFence().matches(job, claimed) or attempt is None:
                raise StaleAttemptError()
            if attempt.status not in {"running", "waiting_callback"}:
                raise StaleAttemptError()
            attempt.status = "waiting_callback"
            if raw_body and runtime.protector is not None:
                attempt.raw_payload_encrypted = runtime.protector.encrypt(raw_body)
            job.status = "waiting_callback"
            job.lease_until = attempt.deadline_at

    async def fail(
        self,
        runtime: PipelineRuntime,
        claimed: ClaimedAttempt,
        error: Exception,
        *,
        callback_token_hash: str | None = None,
        raw_body: bytes | None = None,
        retryable: bool = True,
    ) -> None:
        now = datetime.now(UTC)
        async with runtime.sessions() as session, session.begin():
            job = await session.get(Job, claimed.job_id, with_for_update=True)
            attempt = await session.get(ProcessingAttempt, claimed.attempt_id, with_for_update=True)
            if job is None or not PipelineFence().matches(job, claimed) or attempt is None:
                return
            if attempt.status not in {"running", "waiting_callback"}:
                return
            if callback_token_hash is not None:
                if attempt.callback_token_hash is not None:
                    if attempt.callback_token_hash == callback_token_hash:
                        return
                    raise ClassifierProtocolError("callback token was already used")
                if now > attempt.deadline_at:
                    raise StaleAttemptError("callback deadline has passed")
                attempt.callback_token_hash = callback_token_hash
                attempt.callback_received_at = now
            if raw_body and runtime.protector is not None:
                attempt.raw_payload_encrypted = runtime.protector.encrypt(raw_body)
            detail = type(error).__name__
            attempt.status = "failed"
            attempt.completed_at = now
            attempt.error_code = type(error).__name__
            attempt.error_detail = detail
            job.last_error = detail
            job.owner = None
            job.lease_until = None
            if not retryable or job.attempt_count >= job.max_attempts:
                job.status = "dead_letter"
                job.completed_at = now
            else:
                job.status = "pending"
                delay = runtime.cooldown * 2 ** min(max(job.attempt_count - 1, 0), 8)
                job.available_at = now + timedelta(seconds=delay)
