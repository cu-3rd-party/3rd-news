from __future__ import annotations

import uuid

import pytest
from lib.infra.storage.postgres.labels import SqlAlchemyLabelStorage
from lib.infra.storage.postgres.models import Job, News, OutboxEvent, Source, Submission
from lib.infra.storage.postgres.submissions import (
    SqlAlchemySubmissionIdentityStorage,
    SqlAlchemySubmissionWriterStorage,
)
from lib.infra.storage.postgres.unit_of_work import SqlAlchemyUnitOfWork
from lib.interactor.errors import ConflictError
from lib.interactor.use_cases.submission_acceptance import SubmissionAcceptance
from sqlalchemy import func, select
from thirdnews_contracts import NewsSubmission

pytestmark = pytest.mark.integration


async def test_ingest_is_idempotent_and_outbox_is_atomic(integration_database) -> None:
    source_slug = f"source-{uuid.uuid4().hex}"
    async with integration_database() as session:
        session.add(Source(slug=source_slug, title="Integration source"))
        await session.commit()

    service = SubmissionAcceptance(
        lambda: SqlAlchemyUnitOfWork(integration_database),
        cooldown_seconds=0,
        max_attempts=3,
        label_storage=SqlAlchemyLabelStorage(),
        identity_storage=SqlAlchemySubmissionIdentityStorage(),
        writer_storage=SqlAlchemySubmissionWriterStorage(),
    )
    payload = NewsSubmission(source=source_slug, external_id="42", body_md="Original text")
    first = await service.execute(payload, principal_id="test")
    duplicate = await service.execute(payload, principal_id="test")

    assert first.status == "accepted"
    assert duplicate.status == "duplicate"
    assert duplicate.submission_id == first.submission_id
    async with integration_database() as session:
        submission = await session.get(Submission, first.submission_id)
        news = await session.get(News, submission.news_id)
        assert news.current_version_id is not None
        assert (
            await session.scalar(
                select(func.count()).select_from(Job).where(Job.news_id == news.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.aggregate_id == news.id)
            )
            == 2
        )


async def test_same_identity_with_different_payload_is_conflict(integration_database) -> None:
    source_slug = f"source-{uuid.uuid4().hex}"
    async with integration_database() as session:
        session.add(Source(slug=source_slug, title="Integration source"))
        await session.commit()
    service = SubmissionAcceptance(
        lambda: SqlAlchemyUnitOfWork(integration_database),
        cooldown_seconds=0,
        max_attempts=3,
        label_storage=SqlAlchemyLabelStorage(),
        identity_storage=SqlAlchemySubmissionIdentityStorage(),
        writer_storage=SqlAlchemySubmissionWriterStorage(),
    )
    await service.execute(
        NewsSubmission(source=source_slug, external_id="same", body_md="First"),
        principal_id="test",
    )
    with pytest.raises(ConflictError):
        await service.execute(
            NewsSubmission(source=source_slug, external_id="same", body_md="Changed"),
            principal_id="test",
        )


async def test_equal_text_with_distinct_external_ids_is_not_deduplicated(
    integration_database,
) -> None:
    source_slug = f"source-{uuid.uuid4().hex}"
    async with integration_database() as session:
        session.add(Source(slug=source_slug, title="Integration source"))
        await session.commit()
    service = SubmissionAcceptance(
        lambda: SqlAlchemyUnitOfWork(integration_database),
        cooldown_seconds=0,
        max_attempts=3,
        label_storage=SqlAlchemyLabelStorage(),
        identity_storage=SqlAlchemySubmissionIdentityStorage(),
        writer_storage=SqlAlchemySubmissionWriterStorage(),
    )
    first = await service.execute(
        NewsSubmission(source=source_slug, external_id="one", body_md="Same body"),
        principal_id="test",
    )
    second = await service.execute(
        NewsSubmission(source=source_slug, external_id="two", body_md="Same body"),
        principal_id="test",
    )
    assert first.submission_id != second.submission_id


async def test_idempotency_key_has_same_digest_in_header_and_body(integration_database) -> None:
    source_slug = f"source-{uuid.uuid4().hex}"
    async with integration_database() as session:
        session.add(Source(slug=source_slug, title="Integration source"))
        await session.commit()
    service = SubmissionAcceptance(
        lambda: SqlAlchemyUnitOfWork(integration_database),
        cooldown_seconds=0,
        max_attempts=3,
        label_storage=SqlAlchemyLabelStorage(),
        identity_storage=SqlAlchemySubmissionIdentityStorage(),
        writer_storage=SqlAlchemySubmissionWriterStorage(),
    )
    key = f"header-key-{uuid.uuid4().hex}"
    first = await service.execute(
        NewsSubmission(
            source=source_slug,
            external_id="header-normalization",
            body_md="Same payload",
        ),
        principal_id="test",
        header_idempotency_key=key,
    )
    duplicate = await service.execute(
        NewsSubmission(
            source=source_slug,
            external_id="header-normalization",
            idempotency_key=key,
            body_md="Same payload",
        ),
        principal_id="test",
    )
    assert duplicate.status == "duplicate"
    assert duplicate.submission_id == first.submission_id
