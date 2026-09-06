from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from lib.domain import AcceptedSubmission
from lib.infra.storage.postgres.models import (
    Job,
    News,
    NewsSourceLink,
    NewsVersion,
    OutboxEvent,
    Submission,
)
from lib.interactor.interfaces.storage.labels import LabelStorage
from lib.interactor.interfaces.storage.submission_writer import SubmissionWriterStorage
from lib.interactor.interfaces.storage.unit_of_work import UnitOfWork
from lib.interactor.use_cases.effective_labels import EffectiveLabels

from .attachment_writer import SubmissionAttachmentWriter
from .identity_lookup import SqlAlchemySubmissionIdentityStorage


class SqlAlchemySubmissionWriterStorage(SubmissionWriterStorage):
    async def write(
        self,
        uow: UnitOfWork,
        payload: Any,
        raw: dict[str, Any],
        digest: str,
        source_slug: str | None,
        external_id: str | None,
        idempotency_key: str | None,
        principal_id: str,
        bound_source_id: Any,
        cooldown_seconds: float,
        max_attempts: int,
        label_storage: LabelStorage,
    ) -> AcceptedSubmission:
        source = await SqlAlchemySubmissionIdentityStorage().source(
            uow, source_slug, bound_source_id
        )
        submission = Submission(
            source_id=source.id if source else None,
            external_id=external_id,
            idempotency_key=idempotency_key,
            payload_hash=digest,
            raw_payload=raw,
        )
        news = News()
        version = NewsVersion(
            news=news,
            number=1,
            title=getattr(payload, "title", None),
            body_md=getattr(payload, "body_md", ""),
            source_link=SubmissionAttachmentWriter.string_value(
                getattr(payload, "source_link", None)
            ),
            source_text=getattr(payload, "source_text", None),
            language=getattr(payload, "lang", None) or getattr(payload, "language", None),
            source_published_at=getattr(payload, "published_at", None),
            extra=getattr(payload, "extra", {}) or {},
            created_by=principal_id,
        )
        uow.session.add_all([submission, news, version])
        await uow.session.flush()
        news.current_version_id = version.id
        submission.news_id = news.id
        uow.session.add(NewsSourceLink(news_id=news.id, submission_id=submission.id))
        await SubmissionAttachmentWriter().write(uow, submission, news, payload, principal_id)
        labels = EffectiveLabels(label_storage)
        if source and source.default_labels:
            await labels.record(
                uow.session,
                news,
                source.default_labels,
                origin="source_default",
                origin_key=source.slug,
            )
        initial_labels = getattr(payload, "labels", {}) or {}
        if initial_labels:
            await labels.record(
                uow.session,
                news,
                initial_labels,
                origin="parser",
                origin_key=source.slug if source else principal_id,
            )
        available_at = datetime.now(UTC) + timedelta(seconds=cooldown_seconds)
        job = Job(
            kind="pipeline",
            submission_id=submission.id,
            news_id=news.id,
            available_at=available_at,
            max_attempts=max_attempts,
        )
        uow.session.add(job)
        await uow.session.flush()
        uow.session.add_all(
            [
                OutboxEvent(
                    topic="submission.accepted.v2",
                    aggregate_id=news.id,
                    payload={
                        "submission_id": str(submission.id),
                        "news_id": str(news.id),
                        "revision": news.revision,
                    },
                ),
                OutboxEvent(
                    topic="classification.requested.v2",
                    aggregate_id=news.id,
                    available_at=available_at,
                    payload={
                        "job_id": str(job.id),
                        "news_id": str(news.id),
                        "revision": news.revision,
                    },
                ),
            ]
        )
        await uow.commit()
        return AcceptedSubmission(submission.id, "accepted", submission.received_at)
