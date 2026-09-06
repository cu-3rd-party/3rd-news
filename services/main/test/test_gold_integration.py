from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from lib.dto.claimed_attempt import ClaimedAttempt
from lib.dto.requests import GoldInput
from lib.handlers.admin_gold_export import export, gold
from lib.infra.clients.auth import Principal
from lib.infra.storage.postgres.labels import SqlAlchemyLabelStorage
from lib.infra.storage.postgres.models import (
    AuditLog,
    Classifier,
    Facet,
    FacetValue,
    Job,
    News,
    NewsSourceLink,
    NewsVersion,
    ProcessingAttempt,
    Setting,
    Source,
    Submission,
)
from lib.infra.storage.postgres.pipeline import SqlAlchemyPipelineStorage
from lib.infra.storage.postgres.repositories.context_repository import ContextRepository
from lib.interactor.use_cases.effective_labels import EffectiveLabels
from lib.interactor.use_cases.processing.pipeline_worker import PipelineWorker
from sqlalchemy import select

pytestmark = pytest.mark.integration


async def add_news(session, *, is_gold: bool, marker: str) -> uuid.UUID:
    news = News(status="published", is_gold=is_gold)
    version = NewsVersion(news=news, number=1, title=marker, body_md=f"body {marker}")
    session.add_all([news, version])
    await session.flush()
    news.current_version_id = version.id
    await session.commit()
    return news.id


async def response_lines(response) -> list[dict]:
    raw = b""
    async for chunk in response.body_iterator:
        raw += chunk.encode() if isinstance(chunk, str) else chunk
    return [json.loads(line) for line in raw.splitlines()]


async def test_gold_export_filters_rows_and_batch_marking_is_audited(
    integration_database,
) -> None:
    marker = uuid.uuid4().hex
    async with integration_database() as session:
        gold_id = await add_news(session, is_gold=True, marker=f"gold-{marker}")
        ordinary_id = await add_news(session, is_gold=False, marker=f"ordinary-{marker}")

    principal = Principal("user", "qa-editor", "QA Editor", frozenset({"editor"}))
    async with integration_database() as session:
        before = await response_lines(await export(session, principal, gold_only=True))
        by_id = {item["id"]: item for item in before}
        assert str(gold_id) in by_id
        assert by_id[str(gold_id)]["is_gold"] is True
        assert str(ordinary_id) not in by_id

    async with integration_database() as session:
        result = await gold(GoldInput(ids=[ordinary_id]), session, principal)
        assert result == {"updated": 1}

    async with integration_database() as session:
        marked = await session.get(News, ordinary_id)
        audits = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "gold",
                        AuditLog.entity_type == "news",
                        AuditLog.actor == "user:qa-editor",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert marked is not None and marked.is_gold is True
        assert any(str(ordinary_id) in json.dumps(item.payload) for item in audits)


async def test_gold_news_is_never_injected_as_a_classifier_example(
    integration_database,
) -> None:
    nonce = uuid.uuid4().hex
    async with integration_database() as session:
        classifier = Classifier(
            slug=f"qa-classifier-{nonce}",
            name="QA classifier",
            endpoint="http://classifier.internal",
            enabled=True,
        )
        news = News(status="published", is_gold=True)
        version = NewsVersion(news=news, number=1, title="Gold", body_md="gold body")
        session.add_all([classifier, news, version])
        await session.flush()
        news.current_version_id = version.id
        job = Job(
            kind="classification",
            status="running",
            news_id=news.id,
            classifier_id=classifier.id,
            generation=7,
            payload={"qa_nonce": nonce},
        )
        session.add(job)
        await session.flush()
        attempt = ProcessingAttempt(
            job_id=job.id,
            news_id=news.id,
            version_id=version.id,
            classifier_id=classifier.id,
            generation=7,
            status="running",
            deadline_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        session.add(attempt)
        await session.flush()
        job.current_attempt_id = attempt.id
        context = await session.get(Setting, "classification_context")
        if context is None:
            session.add(
                Setting(
                    key="classification_context",
                    value={"text": "", "examples_enabled": False, "examples_limit": 20},
                )
            )
        else:
            context.value = {
                **context.value,
                "examples_enabled": False,
            }
        await session.commit()
        claimed = ClaimedAttempt(job.id, attempt.id, 7)

    worker = PipelineWorker(
        integration_database,
        cast(Any, object()),
        storage=SqlAlchemyPipelineStorage(),
        node_id="qa",
        public_base_url="https://api.example.test",
        callback_audience="classifier-callback",
    )
    prepared, _endpoint, _node_id, _timeout = await worker.prepare_request(claimed)

    assert prepared.news.id == str(news.id)
    assert prepared.examples == []


async def test_pipeline_uses_bounded_non_gold_manual_examples(
    integration_database,
) -> None:
    nonce = uuid.uuid4().hex
    async with integration_database() as session, session.begin():
        facet = Facet(slug=f"example-{nonce}", title="Example", kind="single")
        classifier = Classifier(
            slug=f"example-classifier-{nonce}",
            name="Example classifier",
            endpoint="http://classifier.internal",
            timeout_seconds=1,
        )
        session.add_all([facet, classifier])
        await session.flush()
        value = FacetValue(facet_id=facet.id, slug="selected", title="Selected")
        session.add(value)
        candidates: list[News] = []
        for title, is_gold in (("ordinary", False), ("gold", True), ("skip", False)):
            news = News(status="published", is_gold=is_gold, published_at=datetime.now(UTC))
            version = NewsVersion(news=news, number=1, title=title, body_md=f"{title} body")
            session.add_all([news, version])
            await session.flush()
            news.current_version_id = version.id
            await EffectiveLabels(SqlAlchemyLabelStorage()).set_manual(
                session,
                news,
                {facet.slug: [value.slug]},
                user_id=None,
            )
            candidates.append(news)
        skip_source = Source(
            slug=f"skip-example-{nonce}",
            title="Skip examples",
            skip_classification=True,
        )
        session.add(skip_source)
        await session.flush()
        submission = Submission(
            source_id=skip_source.id,
            external_id=f"skip-{nonce}",
            payload_hash="0" * 64,
            raw_payload={},
            news_id=candidates[2].id,
        )
        session.add(submission)
        await session.flush()
        session.add(NewsSourceLink(news_id=candidates[2].id, submission_id=submission.id))
        current = News(status="processing")
        current_version = NewsVersion(
            news=current,
            number=1,
            title="Current",
            body_md="current body",
        )
        session.add_all([current, current_version])
        await session.flush()
        current.current_version_id = current_version.id
        job = Job(
            kind="classification",
            status="running",
            news_id=current.id,
            classifier_id=classifier.id,
            generation=1,
        )
        session.add(job)
        await session.flush()
        attempt = ProcessingAttempt(
            job_id=job.id,
            news_id=current.id,
            version_id=current_version.id,
            classifier_id=classifier.id,
            generation=1,
            status="running",
            deadline_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        session.add(attempt)
        await session.flush()
        job.current_attempt_id = attempt.id
        context = await session.get(Setting, "classification_context")
        if context is None:
            session.add(
                Setting(
                    key="classification_context",
                    value={"text": "policy", "examples_enabled": True, "examples_limit": 10},
                )
            )
        else:
            context.value = {
                "text": "policy",
                "examples_enabled": True,
                "examples_limit": 10,
            }
        claimed = ClaimedAttempt(job.id, attempt.id, 1)
        ordinary_id = candidates[0].id
        gold_id = candidates[1].id
        skip_id = candidates[2].id

    worker = PipelineWorker(
        integration_database,
        cast(Any, object()),
        storage=SqlAlchemyPipelineStorage(),
        node_id="qa",
        public_base_url="https://api.example.test",
        callback_audience="classifier-callback",
    )
    prepared, _endpoint, _node_id, timeout = await worker.prepare_request(claimed)
    assert timeout == 1
    example_ids = {item.id for item in prepared.examples}
    assert str(ordinary_id) in example_ids
    assert str(gold_id) not in example_ids
    assert str(skip_id) not in example_ids
    ordinary = next(item for item in prepared.examples if item.id == str(ordinary_id))
    assert ordinary.labels == {facet.slug: [value.slug]}

    async with integration_database() as session:
        stats = await ContextRepository(session).classification_context()
    assert stats["examples_enabled"] is True
    assert stats["example_count"] >= 1
    assert stats["examples_configured"] == 10
    async with integration_database() as session:
        context = await session.get(Setting, "classification_context", with_for_update=True)
        assert context is not None
        context.value = {**context.value, "examples_enabled": False}
        await session.commit()
