from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from lib.infra.storage.postgres.models import (
    Attachment,
    Job,
    News,
    NewsSourceLink,
    NewsVersion,
    ProcessingAttempt,
    Setting,
    Source,
    Submission,
)
from lib.infra.storage.postgres.pipeline_coordinator_storage import (
    SqlAlchemyPipelineCoordinatorStorage,
)
from lib.interactor.use_cases.processing.coordinator import PipelineCoordinator
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def coordinator(database) -> PipelineCoordinator:
    return PipelineCoordinator(
        SqlAlchemyPipelineCoordinatorStorage(
            database,
            node_id="qa-coordinator",
            max_attempts=3,
            cooldown_seconds=1,
            lease_seconds=30,
            poll_seconds=0.01,
        ),
        poll_seconds=0.01,
    )


async def add_running_pipeline(database, *, skip_classification: bool = False):
    nonce = uuid.uuid4().hex
    now = datetime.now(UTC)
    async with database() as session, session.begin():
        news = News(status="processing")
        session.add(news)
        await session.flush()
        version = NewsVersion(news_id=news.id, number=1, body_md="QA", created_by="qa")
        session.add(version)
        await session.flush()
        news.current_version_id = version.id
        parent = Job(
            kind="pipeline",
            status="waiting_children",
            news_id=news.id,
            generation=1,
            attempt_count=1,
            available_at=now,
            payload={},
        )
        session.add(parent)
        await session.flush()
        attempt = ProcessingAttempt(
            job_id=parent.id,
            news_id=news.id,
            version_id=version.id,
            generation=1,
            status="running",
            deadline_at=now + timedelta(hours=1),
        )
        session.add(attempt)
        await session.flush()
        parent.current_attempt_id = attempt.id
        news.current_attempt_id = attempt.id
        parent.payload = {
            "stage": "attachments",
            "children": [],
            "pipeline_attempt_id": str(attempt.id),
            "qa_nonce": nonce,
        }
        if skip_classification:
            source = Source(
                slug=f"skip-{nonce}",
                title="Private QA source",
                skip_classification=True,
            )
            session.add(source)
            await session.flush()
            submission = Submission(
                source_id=source.id,
                external_id=f"qa-{nonce}",
                payload_hash="0" * 64,
                raw_payload={},
                news_id=news.id,
            )
            session.add(submission)
            await session.flush()
            session.add(NewsSourceLink(news_id=news.id, submission_id=submission.id))
        setting = await session.get(Setting, "auto_publish")
        if setting is None:
            session.add(Setting(key="auto_publish", value={"enabled": False}))
        else:
            setting.value = {"enabled": False}
        return news.id, parent.id, attempt.id


async def test_failed_attachment_finishes_pipeline_for_review_and_preserves_failure(
    integration_database,
) -> None:
    news_id, parent_id, attempt_id = await add_running_pipeline(integration_database)
    async with integration_database() as session, session.begin():
        attachment = Attachment(
            news_id=news_id,
            original_url="https://files.example.test/broken.pdf",
            status="failed",
            active=True,
            error="download failed",
        )
        child = Job(
            kind="attachment",
            status="dead_letter",
            news_id=news_id,
            completed_at=datetime.now(UTC),
            last_error="download failed",
            payload={"attachment_id": str(attachment.id)},
        )
        session.add_all([attachment, child])
        await session.flush()
        parent = await session.get(Job, parent_id, with_for_update=True)
        assert parent is not None
        parent.payload = {**parent.payload, "children": [str(child.id)]}
        child_id = child.id

    now = datetime.now(UTC)
    async with integration_database() as session, session.begin():
        parent = await session.get(Job, parent_id, with_for_update=True)
        assert parent is not None
        await coordinator(integration_database).advance(session, parent, now)

    async with integration_database() as session:
        news = await session.get(News, news_id)
        parent = await session.get(Job, parent_id)
        attempt = await session.get(ProcessingAttempt, attempt_id)
        assert news is not None and news.status == "needs_review"
        assert news.current_attempt_id is None
        assert parent is not None and parent.status == "succeeded"
        assert parent.result["children"] == [str(child_id)]
        assert parent.result["failed"] == [str(child_id)]
        assert attempt is not None and attempt.status == "completed_with_errors"
        assert attempt.validated_result == parent.result
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.news_id == news_id, Job.kind == "classification")
            )
            == 0
        )


async def test_source_skip_classification_finishes_without_classifier_jobs(
    integration_database,
) -> None:
    news_id, parent_id, attempt_id = await add_running_pipeline(
        integration_database, skip_classification=True
    )

    now = datetime.now(UTC)
    async with integration_database() as session, session.begin():
        parent = await session.get(Job, parent_id, with_for_update=True)
        assert parent is not None
        await coordinator(integration_database).start_classifiers(session, parent, now)

    async with integration_database() as session:
        news = await session.get(News, news_id)
        parent = await session.get(Job, parent_id)
        attempt = await session.get(ProcessingAttempt, attempt_id)
        assert news is not None and news.status == "needs_review"
        assert parent is not None and parent.status == "succeeded"
        assert parent.result == {"children": [], "failed": [], "published": False}
        assert attempt is not None and attempt.status == "succeeded"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.news_id == news_id, Job.kind == "classification")
            )
            == 0
        )
