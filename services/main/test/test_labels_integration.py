from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from lib.infra.storage.postgres.labels import SqlAlchemyLabelStorage
from lib.infra.storage.postgres.models import (
    Classifier,
    Facet,
    FacetValue,
    Job,
    ManualLabelDecision,
    News,
    NewsEffectiveLabel,
    NewsLabel,
    NewsVersion,
    ProcessingAttempt,
)
from lib.infra.storage.postgres.rematerialization_storage import (
    SqlAlchemyRematerializationStorage,
)
from lib.infra.storage.postgres.repositories import SqlAlchemyNewsAdminRepository
from lib.infra.storage.postgres.repositories.editorial_rule_repository import (
    EditorialRuleRepository,
)
from lib.interactor.use_cases.effective_labels import EffectiveLabels
from lib.interactor.use_cases.rematerialization import RematerializationWorker
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


async def drain_rematerialization(database) -> None:
    worker = RematerializationWorker(
        SqlAlchemyRematerializationStorage(
            database,
            node_id="qa-rematerialization",
            lease_seconds=30,
            cooldown_seconds=0,
        ),
        poll_seconds=0.01,
    )
    for _ in range(100):
        if not await worker.process_one():
            return
    raise AssertionError("rematerialization did not drain")


async def label_fixture(database):
    nonce = uuid.uuid4().hex
    facet = Facet(slug=f"topic-{nonce}", title="Topic", kind="single")
    classifier = Classifier(
        slug=f"classifier-{nonce}",
        name="QA classifier",
        endpoint="https://classifier.example.test",
    )
    news = News()
    version = NewsVersion(news=news, number=1, body_md="Label precedence", created_by="qa")
    async with database() as session:
        session.add_all([facet, classifier, news, version])
        await session.flush()
        session.add_all(
            [
                FacetValue(facet_id=facet.id, slug="official", title="Official"),
                FacetValue(facet_id=facet.id, slug="parser", title="Parser"),
                FacetValue(facet_id=facet.id, slug="ai", title="AI"),
            ]
        )
        news.current_version_id = version.id
        await session.commit()
        return news.id, facet.id, facet.slug, classifier.slug


async def effective_values(session, news_id, facet_id) -> list[str]:
    return list(
        await session.scalars(
            select(FacetValue.slug)
            .join(NewsEffectiveLabel, NewsEffectiveLabel.value_id == FacetValue.id)
            .where(
                NewsEffectiveLabel.news_id == news_id,
                NewsEffectiveLabel.facet_id == facet_id,
            )
            .order_by(FacetValue.slug)
        )
    )


async def successful_classifier_attempt(
    session,
    *,
    news_id,
    version_id,
    classifier: Classifier,
    completed_at: datetime,
) -> ProcessingAttempt:
    job = Job(
        kind="classification",
        status="succeeded",
        news_id=news_id,
        classifier_id=classifier.id,
        completed_at=completed_at,
    )
    session.add(job)
    await session.flush()
    attempt = ProcessingAttempt(
        job_id=job.id,
        news_id=news_id,
        version_id=version_id,
        classifier_id=classifier.id,
        generation=1,
        status="succeeded",
        started_at=completed_at - timedelta(seconds=1),
        deadline_at=completed_at + timedelta(minutes=1),
        completed_at=completed_at,
    )
    session.add(attempt)
    await session.flush()
    job.current_attempt_id = attempt.id
    return attempt


async def test_opinions_are_append_only_and_source_default_outranks_automatic_results(
    integration_database,
) -> None:
    news_id, facet_id, facet_slug, classifier_slug = await label_fixture(integration_database)
    labels = EffectiveLabels(SqlAlchemyLabelStorage())
    async with integration_database() as session, session.begin():
        news = await session.get(News, news_id)
        assert news is not None
        await labels.record(
            session,
            news,
            {facet_slug: ["official"]},
            origin="source_default",
            origin_key="qa-source",
        )
        await labels.record(
            session,
            news,
            {facet_slug: ["parser"]},
            origin="parser",
            origin_key="qa-parser",
        )
        await labels.record(
            session,
            news,
            {facet_slug: ["ai"]},
            origin="classifier",
            origin_key=classifier_slug,
        )

    async with integration_database() as session:
        assert await effective_values(session, news_id, facet_id) == ["official"]
        assert (
            await session.scalar(
                select(func.count()).select_from(NewsLabel).where(NewsLabel.news_id == news_id)
            )
            == 3
        )


async def test_empty_manual_axis_suppresses_automatic_values_until_released(
    integration_database,
) -> None:
    news_id, facet_id, facet_slug, _ = await label_fixture(integration_database)
    labels = EffectiveLabels(SqlAlchemyLabelStorage())
    async with integration_database() as session, session.begin():
        news = await session.get(News, news_id)
        assert news is not None
        await labels.record(
            session,
            news,
            {facet_slug: ["parser"]},
            origin="parser",
            origin_key="qa-parser",
        )
        await labels.set_manual(session, news, {facet_slug: []}, user_id=None)

    async with integration_database() as session:
        assert await effective_values(session, news_id, facet_id) == []
        decisions = (
            await session.scalars(
                select(ManualLabelDecision)
                .where(ManualLabelDecision.news_id == news_id)
                .order_by(ManualLabelDecision.revision)
            )
        ).all()
        assert [(item.revision, item.action) for item in decisions] == [(1, "set")]

    async with integration_database() as session, session.begin():
        news = await session.get(News, news_id)
        assert news is not None
        await labels.release(session, news, [facet_slug])
    async with integration_database() as session:
        assert await effective_values(session, news_id, facet_id) == ["parser"]
        decisions = (
            await session.scalars(
                select(ManualLabelDecision)
                .where(ManualLabelDecision.news_id == news_id)
                .order_by(ManualLabelDecision.revision)
            )
        ).all()
        assert [(item.revision, item.action) for item in decisions] == [
            (1, "set"),
            (2, "release"),
        ]


async def test_single_facet_uses_only_highest_priority_classifier_opinion(
    integration_database,
) -> None:
    news_id, facet_id, facet_slug, low_slug = await label_fixture(integration_database)
    now = datetime.now(UTC)
    labels = EffectiveLabels(SqlAlchemyLabelStorage())
    async with integration_database() as session, session.begin():
        news = await session.get(News, news_id)
        low = await session.scalar(select(Classifier).where(Classifier.slug == low_slug))
        assert news is not None and news.current_version_id is not None and low is not None
        low.priority = 10
        high = Classifier(
            slug=f"high-{uuid.uuid4().hex}",
            name="High priority QA classifier",
            endpoint="https://high-classifier.example.test",
            priority=500,
        )
        session.add(high)
        await session.flush()
        low_attempt = await successful_classifier_attempt(
            session,
            news_id=news.id,
            version_id=news.current_version_id,
            classifier=low,
            completed_at=now,
        )
        high_attempt = await successful_classifier_attempt(
            session,
            news_id=news.id,
            version_id=news.current_version_id,
            classifier=high,
            completed_at=now,
        )
        await labels.record(
            session,
            news,
            {facet_slug: ["parser"]},
            origin="classifier",
            origin_key=f"{low.slug}:{low_attempt.id}",
        )
        await labels.record(
            session,
            news,
            {facet_slug: ["ai"]},
            origin="classifier",
            origin_key=f"{high.slug}:{high_attempt.id}",
        )

    async with integration_database() as session:
        assert await effective_values(session, news_id, facet_id) == ["ai"]


async def test_new_empty_classifier_opinion_revokes_previous_attempt_values(
    integration_database,
) -> None:
    news_id, facet_id, facet_slug, classifier_slug = await label_fixture(integration_database)
    now = datetime.now(UTC)
    labels = EffectiveLabels(SqlAlchemyLabelStorage())
    async with integration_database() as session, session.begin():
        news = await session.get(News, news_id)
        classifier = await session.scalar(
            select(Classifier).where(Classifier.slug == classifier_slug)
        )
        assert news is not None and news.current_version_id is not None and classifier is not None
        old = await successful_classifier_attempt(
            session,
            news_id=news.id,
            version_id=news.current_version_id,
            classifier=classifier,
            completed_at=now - timedelta(minutes=1),
        )
        await labels.record(
            session,
            news,
            {facet_slug: ["ai"]},
            origin="classifier",
            origin_key=f"{classifier.slug}:{old.id}",
        )

    async with integration_database() as session:
        assert await effective_values(session, news_id, facet_id) == ["ai"]

    async with integration_database() as session, session.begin():
        news = await session.get(News, news_id)
        classifier = await session.scalar(
            select(Classifier).where(Classifier.slug == classifier_slug)
        )
        assert news is not None and news.current_version_id is not None and classifier is not None
        await successful_classifier_attempt(
            session,
            news_id=news.id,
            version_id=news.current_version_id,
            classifier=classifier,
            completed_at=now,
        )
        await labels.recompute(session, news)

    async with integration_database() as session:
        assert await effective_values(session, news_id, facet_id) == []
        assert (
            await session.scalar(
                select(func.count()).select_from(NewsLabel).where(NewsLabel.news_id == news_id)
            )
            == 1
        )


async def test_shadow_classifier_opinion_is_audited_but_never_effective(
    integration_database,
) -> None:
    news_id, facet_id, facet_slug, classifier_slug = await label_fixture(integration_database)
    now = datetime.now(UTC)
    labels = EffectiveLabels(SqlAlchemyLabelStorage())
    async with integration_database() as session, session.begin():
        news = await session.get(News, news_id)
        classifier = await session.scalar(
            select(Classifier).where(Classifier.slug == classifier_slug)
        )
        assert news is not None and news.current_version_id is not None and classifier is not None
        classifier.shadow = True
        attempt = await successful_classifier_attempt(
            session,
            news_id=news.id,
            version_id=news.current_version_id,
            classifier=classifier,
            completed_at=now,
        )
        await labels.record(
            session,
            news,
            {facet_slug: ["ai"]},
            origin="shadow",
            origin_key=f"{classifier.slug}:{attempt.id}",
        )

    async with integration_database() as session:
        assert await effective_values(session, news_id, facet_id) == []
        assert (
            await session.scalar(
                select(func.count())
                .select_from(NewsLabel)
                .where(NewsLabel.news_id == news_id, NewsLabel.origin == "shadow")
            )
            == 1
        )


async def test_rule_revision_and_manual_empty_recalculate_scores(
    integration_database,
) -> None:
    news_id, _facet_id, facet_slug, _ = await label_fixture(integration_database)
    labels = EffectiveLabels(SqlAlchemyLabelStorage())
    async with integration_database() as session, session.begin():
        news = await session.get(News, news_id)
        assert news is not None
        await labels.record(
            session,
            news,
            {facet_slug: ["official"]},
            origin="source_default",
            origin_key="qa-source",
        )

    async with integration_database() as session:
        await EditorialRuleRepository(session).create_editorial_rule(
            {
                "name": f"score-{uuid.uuid4().hex}",
                "enabled": True,
                "definition": {
                    "when": {facet_slug: "official"},
                    "set": {"urgency": 91},
                },
            },
            "qa",
        )
    await drain_rematerialization(integration_database)

    async with integration_database() as session:
        scored = await session.get(News, news_id)
        assert scored is not None
        assert (scored.urgency, scored.importance) == (91, 91)
        await SqlAlchemyNewsAdminRepository(session).manual_labels(
            news_id,
            labels={facet_slug: []},
            release_facets=[],
            user_id=None,
            actor="qa",
        )

    async with integration_database() as session:
        cleared = await session.get(News, news_id)
        assert cleared is not None
        assert (cleared.urgency, cleared.importance) == (0, 0)
