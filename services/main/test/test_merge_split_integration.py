from __future__ import annotations

import hashlib
import uuid

import pytest
from lib.infra.storage.postgres.labels import SqlAlchemyLabelStorage
from lib.infra.storage.postgres.models import (
    Attachment,
    Facet,
    FacetValue,
    ManualLabelDecision,
    News,
    NewsLabel,
    NewsSourceLink,
    NewsVersion,
    Submission,
)
from lib.infra.storage.postgres.news_administration import (
    SqlAlchemyNewsMergeStorage,
    SqlAlchemyNewsSplitStorage,
)
from lib.interactor.use_cases.effective_labels import EffectiveLabels
from lib.interactor.use_cases.news_merge import NewsMerge
from lib.interactor.use_cases.news_split import NewsSplit
from sqlalchemy import select

pytestmark = pytest.mark.integration


async def aggregate(session, marker: str) -> tuple[News, Submission, Attachment]:
    payload = {"body_md": marker}
    news = News(status="needs_review")
    version = NewsVersion(news=news, number=1, body_md=marker, created_by="qa")
    submission = Submission(
        idempotency_key=f"qa-{uuid.uuid4()}",
        payload_hash=hashlib.sha256(marker.encode()).hexdigest(),
        raw_payload=payload,
    )
    session.add_all([news, version, submission])
    await session.flush()
    news.current_version_id = version.id
    submission.news_id = news.id
    link = NewsSourceLink(news_id=news.id, submission_id=submission.id)
    attachment = Attachment(
        news_id=news.id,
        submission_id=submission.id,
        kind="file",
        status="stored",
        object_key=f"qa/{uuid.uuid4()}",
        size=1,
        sha256=hashlib.sha256(b"x").hexdigest(),
    )
    session.add_all([link, attachment])
    await session.flush()
    return news, submission, attachment


async def test_merge_and_split_move_attachments_and_copy_opinion_provenance(
    integration_database,
) -> None:
    async with integration_database() as session, session.begin():
        target, target_submission, _ = await aggregate(session, "target")
        source, source_submission, source_attachment = await aggregate(session, "source")
        facet = Facet(slug=f"qa-{uuid.uuid4().hex}", title="QA", kind="single")
        session.add(facet)
        await session.flush()
        value = FacetValue(facet_id=facet.id, slug="value", title="Value")
        empty_facet = Facet(slug=f"qa-empty-{uuid.uuid4().hex}", title="Empty", kind="single")
        session.add_all([value, empty_facet])
        await session.flush()
        session.add(
            NewsLabel(
                news_id=source.id,
                version_id=source.current_version_id,
                facet_id=facet.id,
                value_id=value.id,
                origin="manual",
                origin_key="qa-editor",
            )
        )
        await EffectiveLabels(SqlAlchemyLabelStorage()).set_manual(
            session,
            source,
            {empty_facet.slug: []},
            user_id=None,
        )
        target_id = target.id
        target_submission_id = target_submission.id
        source_id = source.id
        source_submission_id = source_submission.id
        source_attachment_id = source_attachment.id

    async with integration_database() as session, session.begin():
        service = NewsMerge(SqlAlchemyNewsMergeStorage())
        target = await service.get(session, target_id, lock=True)
        await service.merge(session, target, [source_id], "qa")

    async with integration_database() as session:
        moved = await session.get(Attachment, source_attachment_id)
        provenance = (
            await session.scalars(
                select(NewsLabel).where(
                    NewsLabel.news_id == target_id,
                    NewsLabel.origin == "provenance",
                )
            )
        ).all()
        empty_provenance = (
            await session.scalars(
                select(ManualLabelDecision).where(
                    ManualLabelDecision.news_id == target_id,
                    ManualLabelDecision.facet_id == empty_facet.id,
                    ManualLabelDecision.origin == "provenance",
                    ManualLabelDecision.action == "set",
                )
            )
        ).all()
        assert moved is not None and moved.news_id == target_id
        assert provenance and provenance[0].evidence["source_news_id"] == str(source_id)
        assert len(empty_provenance) == 1
        empty_facet_id = empty_facet.id

    async with integration_database() as session, session.begin():
        target = await session.get(News, target_id, with_for_update=True)
        assert target is not None
        await EffectiveLabels(SqlAlchemyLabelStorage()).set_manual(
            session,
            target,
            {empty_facet.slug: []},
            user_id=None,
        )

    async with integration_database() as session:
        decisions = (
            await session.scalars(
                select(ManualLabelDecision)
                .where(
                    ManualLabelDecision.news_id == target_id,
                    ManualLabelDecision.facet_id == empty_facet_id,
                )
                .order_by(ManualLabelDecision.revision)
            )
        ).all()
        assert [(item.origin, item.revision) for item in decisions] == [
            ("provenance", 1),
            ("manual", 2),
        ]

    async with integration_database() as session, session.begin():
        service = NewsSplit(SqlAlchemyNewsSplitStorage())
        target = await service.get(session, target_id, lock=True)
        created = await service.split(session, target, [source_submission_id], "qa")
        created_id = created.id

    async with integration_database() as session:
        moved = await session.get(Attachment, source_attachment_id)
        source_submission = await session.get(Submission, source_submission_id)
        target_submission = await session.get(Submission, target_submission_id)
        split_empty_provenance = (
            await session.scalars(
                select(ManualLabelDecision).where(
                    ManualLabelDecision.news_id == created_id,
                    ManualLabelDecision.facet_id == empty_facet_id,
                    ManualLabelDecision.origin == "provenance",
                    ManualLabelDecision.action == "set",
                )
            )
        ).all()
        assert moved is not None and moved.news_id == created_id
        assert source_submission is not None and source_submission.news_id == created_id
        assert target_submission is not None and target_submission.news_id == target_id
        assert split_empty_provenance
