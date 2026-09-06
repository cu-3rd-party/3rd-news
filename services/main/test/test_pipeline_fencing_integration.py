from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from lib.dto.claimed_attempt import ClaimedAttempt
from lib.infra.storage.postgres.models import (
    Classifier,
    Facet,
    FacetValue,
    Job,
    News,
    NewsEffectiveLabel,
    NewsVersion,
    ProcessingAttempt,
)
from lib.infra.storage.postgres.pipeline import SqlAlchemyPipelineStorage
from lib.interactor.errors.classifier_protocol import ClassifierProtocolError
from lib.interactor.errors.stale_attempt import StaleAttemptError
from lib.interactor.use_cases.processing.pipeline_worker import PipelineWorker
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from thirdnews_contracts import (
    ClassificationStatus,
    ClassifyResponse,
    ProposedLabel,
)

pytestmark = pytest.mark.integration


class UnusedClassifierClient:
    async def classify(self, *args, **kwargs):
        raise AssertionError("claim/fencing tests must not perform HTTP")


def worker(database, node_id: str) -> PipelineWorker:
    return PipelineWorker(
        database,
        cast(Any, UnusedClassifierClient()),
        storage=SqlAlchemyPipelineStorage(),
        node_id=node_id,
        public_base_url="https://api.example.test",
        callback_audience="thirdnews-callback",
        lease_seconds=30,
    )


async def add_classification_job(database, *, max_attempts: int = 3) -> uuid.UUID:
    async with database() as session, session.begin():
        await session.execute(delete(Job).where(Job.payload.op("?")("qa_nonce")))
    job = Job(
        kind="classification",
        status="pending",
        available_at=datetime(2000, 1, 1, tzinfo=UTC),
        max_attempts=max_attempts,
        payload={"qa_nonce": str(uuid.uuid4())},
    )
    async with database() as session:
        session.add(job)
        await session.commit()
        return job.id


async def add_jobs_for_one_news(database) -> tuple[uuid.UUID, set[uuid.UUID]]:
    news = News(status="pending")
    async with database() as session:
        session.add(news)
        await session.flush()
        jobs = [
            Job(
                kind="classification",
                status="pending",
                news_id=news.id,
                available_at=datetime(2000, 1, 1, tzinfo=UTC),
                payload={"qa_nonce": str(uuid.uuid4())},
            )
            for _ in range(2)
        ]
        session.add_all(jobs)
        await session.commit()
        return news.id, {job.id for job in jobs}


async def test_skip_locked_allows_only_one_worker_to_claim_job(integration_database) -> None:
    job_id = await add_classification_job(integration_database)
    claimed = await asyncio.gather(
        worker(integration_database, "node-a").claim_one(),
        worker(integration_database, "node-b").claim_one(),
    )

    winners = [item for item in claimed if item is not None and item.job_id == job_id]
    assert len(winners) == 1
    async with integration_database() as session:
        job = await session.get(Job, job_id)
        attempts = list(
            await session.scalars(
                select(ProcessingAttempt).where(ProcessingAttempt.job_id == job_id)
            )
        )
        assert job is not None
        assert job.attempt_count == 1
        assert job.current_attempt_id == winners[0].attempt_id
        assert len(attempts) == 1


async def test_concurrent_jobs_for_one_news_do_not_deadlock_claimers(
    integration_database,
    monkeypatch,
) -> None:
    _news_id, job_ids = await add_jobs_for_one_news(integration_database)
    original_flush = AsyncSession.flush
    both_attempts_inserted = asyncio.Event()
    inserted = 0

    async def synchronize_attempt_inserts(session, *args, **kwargs):
        nonlocal inserted
        inserting_attempt = any(isinstance(item, ProcessingAttempt) for item in session.new)
        await original_flush(session, *args, **kwargs)
        if inserting_attempt:
            inserted += 1
            if inserted == 2:
                both_attempts_inserted.set()
            await asyncio.wait_for(both_attempts_inserted.wait(), timeout=3)

    monkeypatch.setattr(AsyncSession, "flush", synchronize_attempt_inserts)

    claimed = await asyncio.wait_for(
        asyncio.gather(
            worker(integration_database, "node-a").claim_one(),
            worker(integration_database, "node-b").claim_one(),
        ),
        timeout=5,
    )

    assert {item.job_id for item in claimed if item is not None} == job_ids


async def test_expired_lease_fences_old_worker_and_records_timeout(integration_database) -> None:
    job_id = await add_classification_job(integration_database)
    first_worker = worker(integration_database, "old-node")
    first = await first_worker.claim_one()
    assert first is not None and first.job_id == job_id

    async with integration_database() as session, session.begin():
        job = await session.get(Job, job_id, with_for_update=True)
        assert job is not None
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)

    replacement = await worker(integration_database, "new-node").claim_one()
    assert replacement is not None and replacement.job_id == job_id
    assert replacement.generation > first.generation
    with pytest.raises(StaleAttemptError):
        await first_worker.mark_waiting(first, b"late result")

    async with integration_database() as session:
        job = await session.get(Job, job_id)
        stale = await session.get(ProcessingAttempt, first.attempt_id)
        current = await session.get(ProcessingAttempt, replacement.attempt_id)
        assert job is not None and job.current_attempt_id == replacement.attempt_id
        assert stale is not None and stale.status == "timed_out"
        assert stale.error_code == "deadline_exceeded"
        assert current is not None and current.status == "running"


async def test_attempt_budget_moves_expired_job_to_dead_letter(integration_database) -> None:
    job_id = await add_classification_job(integration_database, max_attempts=1)
    first = await worker(integration_database, "node-a").claim_one()
    assert first is not None and first.job_id == job_id
    async with integration_database() as session, session.begin():
        job = await session.get(Job, job_id, with_for_update=True)
        assert job is not None
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)

    assert await worker(integration_database, "node-b").claim_one() is None
    async with integration_database() as session:
        job = await session.get(Job, job_id)
        attempt = await session.get(ProcessingAttempt, first.attempt_id)
        assert job is not None and job.status == "dead_letter"
        assert job.completed_at is not None
        assert attempt is not None and attempt.status == "timed_out"


@pytest.mark.parametrize(
    ("retryable", "expected_status"),
    [(True, "pending"), (False, "dead_letter")],
)
async def test_classifier_failure_honours_retryability(
    integration_database, retryable: bool, expected_status: str
) -> None:
    job_id = await add_classification_job(integration_database, max_attempts=3)
    pipeline = worker(integration_database, "failure-node")
    claimed = await pipeline.claim_one()
    assert claimed is not None and claimed.job_id == job_id

    await pipeline.fail(
        claimed,
        ClassifierProtocolError("classifier_failed:provider_error"),
        retryable=retryable,
    )

    async with integration_database() as session:
        job = await session.get(Job, job_id)
        attempt = await session.get(ProcessingAttempt, claimed.attempt_id)
        assert job is not None and job.status == expected_status
        assert attempt is not None and attempt.status == "failed"


async def test_successful_response_materialises_current_attempt_labels(
    integration_database,
) -> None:
    nonce = uuid.uuid4().hex
    async with integration_database() as session, session.begin():
        facet = Facet(slug=f"pipeline-{nonce}", title="Pipeline", kind="single")
        classifier = Classifier(
            slug=f"pipeline-classifier-{nonce}",
            name="Pipeline classifier",
            endpoint="https://classifier.example.test",
            config={"node_id": "pipeline-node"},
        )
        news = News(status="processing")
        version = NewsVersion(news=news, number=1, body_md="pipeline", created_by="qa")
        session.add_all([facet, classifier, news, version])
        await session.flush()
        value = FacetValue(facet_id=facet.id, slug="selected", title="Selected")
        session.add(value)
        news.current_version_id = version.id
        job = Job(
            kind="classification",
            status="running",
            news_id=news.id,
            classifier_id=classifier.id,
            generation=1,
            attempt_count=1,
            owner="pipeline-node",
        )
        session.add(job)
        await session.flush()
        attempt = ProcessingAttempt(
            job_id=job.id,
            news_id=news.id,
            version_id=version.id,
            classifier_id=classifier.id,
            generation=1,
            status="running",
            deadline_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        session.add(attempt)
        await session.flush()
        job.current_attempt_id = attempt.id
        claimed = ClaimedAttempt(job.id, attempt.id, 1)
        ids = (news.id, facet.id, value.id, job.id, attempt.id, classifier.slug)

    news_id, facet_id, _value_id, job_id, attempt_id, classifier_slug = ids
    response = ClassifyResponse(
        request_id="request",
        job_id=str(job_id),
        attempt_id=str(attempt_id),
        news_id=str(news_id),
        news_version=1,
        classifier=classifier_slug,
        node_id="pipeline-node",
        status=ClassificationStatus.COMPLETED,
        labels=[ProposedLabel(axis=f"pipeline-{nonce}", value="selected", confidence=0.9)],
    )
    await worker(integration_database, "pipeline-node").apply_response(
        claimed, response, response.model_dump_json().encode()
    )

    async with integration_database() as session:
        job = await session.get(Job, job_id)
        attempt = await session.get(ProcessingAttempt, attempt_id)
        effective = (
            await session.scalars(
                select(NewsEffectiveLabel).where(
                    NewsEffectiveLabel.news_id == news_id,
                    NewsEffectiveLabel.facet_id == facet_id,
                )
            )
        ).all()
        assert job is not None and job.status == "succeeded"
        assert attempt is not None and attempt.status == "succeeded"
        assert len(effective) == 1
