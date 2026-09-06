from __future__ import annotations

import asyncio
import uuid

import pytest
from lib.infra.storage.postgres.labels import SqlAlchemyLabelStorage
from lib.infra.storage.postgres.models import Job, News, OutboxEvent, Source, Submission
from lib.infra.storage.postgres.submissions import (
    SqlAlchemySubmissionIdentityStorage,
    SqlAlchemySubmissionWriterStorage,
)
from lib.infra.storage.postgres.unit_of_work import SqlAlchemyUnitOfWork
from lib.interactor.use_cases.submission_acceptance import SubmissionAcceptance
from sqlalchemy import func, select
from thirdnews_contracts import NewsSubmission

pytestmark = pytest.mark.integration


class SynchronizedSubmissionIdentityLookup(SqlAlchemySubmissionIdentityStorage):
    def __init__(self, barrier: asyncio.Barrier) -> None:
        self.barrier = barrier

    async def find(self, uow, identity, bound_source_id):
        existing = await super().find(uow, identity, bound_source_id)
        if existing is None:
            await self.barrier.wait()
        return existing


async def test_concurrent_identical_ingest_creates_one_aggregate(integration_database) -> None:
    source_slug = f"qa-concurrent-{uuid.uuid4().hex}"
    async with integration_database() as session:
        session.add(Source(slug=source_slug, title="Concurrent QA source"))
        await session.commit()

    barrier = asyncio.Barrier(2)
    service = SubmissionAcceptance(
        lambda: SqlAlchemyUnitOfWork(integration_database),
        cooldown_seconds=0,
        max_attempts=3,
        label_storage=SqlAlchemyLabelStorage(),
        identity_storage=SynchronizedSubmissionIdentityLookup(barrier),
        writer_storage=SqlAlchemySubmissionWriterStorage(),
    )
    payload = NewsSubmission(
        source=source_slug,
        external_id=f"same-{uuid.uuid4()}",
        body_md="Exactly one aggregate must survive the race",
    )
    results = await asyncio.wait_for(
        asyncio.gather(
            service.execute(payload, principal_id="qa-a"),
            service.execute(payload, principal_id="qa-b"),
        ),
        timeout=10,
    )

    assert sorted(item.status for item in results) == ["accepted", "duplicate"]
    assert results[0].submission_id == results[1].submission_id
    async with integration_database() as session:
        submission = await session.get(Submission, results[0].submission_id)
        assert submission is not None and submission.news_id is not None
        assert (
            await session.scalar(
                select(func.count()).select_from(News).where(News.id == submission.news_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(Job).where(Job.news_id == submission.news_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.aggregate_id == submission.news_id)
            )
            == 2
        )
