from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from lib.core.config import REMATERIALIZATION_JOB_KIND
from lib.infra.storage.postgres.labels import SqlAlchemyLabelStorage
from lib.infra.storage.postgres.models import (
    Classifier,
    Facet,
    FacetValue,
    Job,
    News,
    NewsEffectiveLabel,
    NewsLabel,
    NewsVersion,
    ProcessingAttempt,
    Setting,
)
from lib.infra.storage.postgres.pipeline import PipelineTaxonomy
from lib.infra.storage.postgres.rematerialization_storage import (
    SqlAlchemyRematerializationStorage,
)
from lib.infra.storage.postgres.repositories import (
    PersistenceRepository,
    SqlAlchemyNewsDeliveryRepository,
    SqlAlchemyTaxonomyRepository,
)
from lib.infra.storage.postgres.repositories.classifier_repository import ClassifierRepository
from lib.interactor.use_cases.effective_labels import EffectiveLabels
from lib.interactor.use_cases.rematerialization import RematerializationWorker
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def worker(database, *, batch_size: int = 50) -> RematerializationWorker:
    return RematerializationWorker(
        SqlAlchemyRematerializationStorage(
            database,
            node_id="qa-rematerialization",
            lease_seconds=30,
            cooldown_seconds=0,
            batch_size=batch_size,
        ),
        poll_seconds=0.01,
    )


async def drain(database) -> None:
    current = worker(database)
    for _ in range(100):
        if not await current.process_one():
            return
    raise AssertionError("rematerialization did not drain")


async def classifier_fixture(database):
    nonce = uuid.uuid4().hex
    async with database() as session, session.begin():
        facet = Facet(slug=f"policy-{nonce}", title="Policy", kind="single")
        classifier = Classifier(
            slug=f"policy-node-{nonce}",
            name="Policy node",
            endpoint="https://classifier.example.test",
            signing_public_key="stable-public-key",
        )
        news = News(status="published", published_at=datetime.now(UTC))
        version = NewsVersion(news=news, number=1, body_md="policy body", created_by="qa")
        session.add_all([facet, classifier, news, version])
        await session.flush()
        value = FacetValue(facet_id=facet.id, slug="private", title="Private")
        session.add(value)
        news.current_version_id = version.id
        job = Job(
            kind="classification",
            status="succeeded",
            news_id=news.id,
            classifier_id=classifier.id,
            completed_at=datetime.now(UTC),
        )
        session.add(job)
        await session.flush()
        attempt = ProcessingAttempt(
            job_id=job.id,
            news_id=news.id,
            version_id=version.id,
            classifier_id=classifier.id,
            generation=1,
            status="succeeded",
            deadline_at=datetime.now(UTC) + timedelta(minutes=1),
            completed_at=datetime.now(UTC),
        )
        session.add(attempt)
        await session.flush()
        job.current_attempt_id = attempt.id
        session.add(
            NewsLabel(
                news_id=news.id,
                version_id=version.id,
                facet_id=facet.id,
                value_id=value.id,
                origin="classifier",
                origin_key=f"{classifier.slug}:{attempt.id}",
                confidence=0.75,
            )
        )
        await session.flush()
        await EffectiveLabels(SqlAlchemyLabelStorage()).recompute(session, news)
        return news.id, facet.id, classifier.id, classifier.slug


async def effective_count(database, news_id: uuid.UUID) -> int:
    async with database() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(NewsEffectiveLabel)
                .where(NewsEffectiveLabel.news_id == news_id)
            )
            or 0
        )


async def test_classifier_policy_change_closes_barrier_and_rematerializes_history(
    integration_database,
) -> None:
    news_id, _facet_id, classifier_id, classifier_slug = await classifier_fixture(
        integration_database
    )
    assert await effective_count(integration_database, news_id) == 1

    async with integration_database() as session:
        await ClassifierRepository(session).update_classifier(classifier_id, {"shadow": True}, "qa")
    async with integration_database() as session:
        assert not await SqlAlchemyNewsDeliveryRepository(session).visibility_ready()
        classifier = await session.get(Classifier, classifier_id)
        assert classifier is not None and classifier.signing_public_key == "stable-public-key"
        pending = await session.scalar(
            select(Job).where(
                Job.kind == REMATERIALIZATION_JOB_KIND,
                Job.status == "pending",
                Job.payload["scope_id"].as_string() == classifier_slug,
            )
        )
        assert pending is not None

    await drain(integration_database)
    assert await effective_count(integration_database, news_id) == 0

    async with integration_database() as session:
        await ClassifierRepository(session).update_classifier(
            classifier_id, {"shadow": False}, "qa"
        )
    await drain(integration_database)
    assert await effective_count(integration_database, news_id) == 1

    async with integration_database() as session:
        await ClassifierRepository(session).update_classifier(
            classifier_id, {"min_confidence": 1.0}, "qa"
        )
    await drain(integration_database)
    assert await effective_count(integration_database, news_id) == 0

    async with integration_database() as session:
        await ClassifierRepository(session).update_classifier(
            classifier_id, {"min_confidence": 0.5}, "qa"
        )
    await drain(integration_database)
    assert await effective_count(integration_database, news_id) == 1

    async with integration_database() as session:
        await ClassifierRepository(session).delete_classifier(classifier_id, "qa")
    async with integration_database() as session:
        assert not await SqlAlchemyNewsDeliveryRepository(session).visibility_ready()
    await drain(integration_database)
    assert await effective_count(integration_database, news_id) == 0


async def test_taxonomy_disable_enable_uses_immutable_opinions(
    integration_database,
) -> None:
    news_id, facet_id, _classifier_id, _classifier_slug = await classifier_fixture(
        integration_database
    )
    async with integration_database() as session, session.begin():
        facet = await session.get(Facet, facet_id)
        assert facet is not None
        empty_news = News(status="published", published_at=datetime.now(UTC))
        empty_version = NewsVersion(
            news=empty_news,
            number=1,
            body_md="explicit empty taxonomy policy",
            created_by="qa",
        )
        session.add_all([empty_news, empty_version])
        await session.flush()
        empty_news.current_version_id = empty_version.id
        await EffectiveLabels(SqlAlchemyLabelStorage()).set_manual(
            session,
            empty_news,
            {facet.slug: []},
            user_id=None,
        )
        empty_news_id = empty_news.id
        facet_slug = facet.slug
    async with integration_database() as session:
        before = await session.get(Setting, "taxonomy_revision")
        before_revision = int((before.value if before else {}).get("revision") or 0)
        repository = SqlAlchemyTaxonomyRepository(session)
        facet = await session.get(Facet, facet_id)
        assert facet is not None
        values = repository._facet_values(facet)
        await repository.update_facet(facet_id, {**values, "enabled": False}, "qa")
    await drain(integration_database)
    assert await effective_count(integration_database, news_id) == 0
    async with integration_database() as session:
        empty_news = await session.get(News, empty_news_id)
        assert empty_news is not None and empty_news.manual_facets == []

    async with integration_database() as session:
        repository = SqlAlchemyTaxonomyRepository(session)
        facet = await session.get(Facet, facet_id)
        assert facet is not None
        values = repository._facet_values(facet)
        await repository.update_facet(facet_id, {**values, "enabled": True}, "qa")
    await drain(integration_database)
    assert await effective_count(integration_database, news_id) == 1
    async with integration_database() as session:
        empty_news = await session.get(News, empty_news_id)
        assert empty_news is not None and empty_news.manual_facets == [facet_slug]
        after = await session.get(Setting, "taxonomy_revision")
        assert after is not None
        assert int(after.value["revision"]) == before_revision + 2


async def test_value_change_advances_one_canonical_taxonomy_revision(
    integration_database,
) -> None:
    _news_id, facet_id, _classifier_id, _classifier_slug = await classifier_fixture(
        integration_database
    )
    async with integration_database() as session:
        before = await session.get(Setting, "taxonomy_revision")
        before_revision = int((before.value if before else {}).get("revision") or 0)
        value = await session.scalar(select(FacetValue).where(FacetValue.facet_id == facet_id))
        assert value is not None
        repository = SqlAlchemyTaxonomyRepository(session)
        values = repository._value_values(value)
        values["ai_hint"] = "revised meaning"
        await repository.update_value(value.id, values, "qa")

    async with integration_database() as session:
        public = await SqlAlchemyNewsDeliveryRepository(session).taxonomy()
        classifier, _definitions = await PipelineTaxonomy().load(session)
        assert public["version"] == classifier.version == str(before_revision + 1)

    await drain(integration_database)


async def test_rematerialization_advances_in_bounded_chunks(integration_database) -> None:
    news_id, facet_id, _classifier_id, _classifier_slug = await classifier_fixture(
        integration_database
    )
    async with integration_database() as session, session.begin():
        original = await session.get(News, news_id)
        assert original is not None and original.current_version_id is not None
        for index in range(2):
            news = News(status="published", published_at=datetime.now(UTC))
            version = NewsVersion(news=news, number=1, body_md=f"chunk {index}", created_by="qa")
            session.add_all([news, version])
            await session.flush()
            news.current_version_id = version.id
            source_label = await session.scalar(
                select(NewsLabel).where(NewsLabel.news_id == original.id).limit(1)
            )
            assert source_label is not None
            session.add(
                NewsLabel(
                    news_id=news.id,
                    version_id=version.id,
                    facet_id=facet_id,
                    value_id=source_label.value_id,
                    origin="parser",
                    origin_key=f"chunk-{index}",
                )
            )
        job = PersistenceRepository(session).enqueue_rematerialization(
            scope="facet", scope_id=facet_id
        )
        await session.flush()
        job_id = job.id

    current = worker(integration_database, batch_size=1)
    assert await current.process_one()
    async with integration_database() as session:
        job = await session.get(Job, job_id)
        assert job is not None and job.status == "pending" and job.payload.get("cursor")
    await drain(integration_database)
    async with integration_database() as session:
        job = await session.get(Job, job_id)
        assert job is not None and job.status == "succeeded"
