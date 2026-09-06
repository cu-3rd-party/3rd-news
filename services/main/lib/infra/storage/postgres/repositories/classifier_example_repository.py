from __future__ import annotations

import uuid

from lib.core.config import CLASSIFIER_EXAMPLE_BODY_MAX_CHARACTERS
from lib.infra.storage.postgres.models import (
    Facet,
    FacetValue,
    ManualLabelDecision,
    News,
    NewsLabel,
    NewsSourceLink,
    NewsVersion,
    Source,
    Submission,
)
from lib.interactor.interfaces.storage.classifier_example import ClassifierExampleStorage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from thirdnews_contracts import LabeledExample


class ClassifierExampleRepository(ClassifierExampleStorage):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_examples(
        self,
        *,
        exclude_news_id: uuid.UUID | None,
        allowed_axes: set[str],
        limit: int,
    ) -> list[LabeledExample]:
        query = self._eligible_query()
        if exclude_news_id is not None:
            query = query.where(News.id != exclude_news_id)
        rows = (
            await self.session.execute(query.order_by(News.updated_at.desc(), News.id).limit(limit))
        ).all()
        examples: list[LabeledExample] = []
        for news, version in rows:
            labels = await self._latest_labels(news.id, version.id, allowed_axes)
            if not labels:
                continue
            examples.append(
                LabeledExample(
                    id=str(news.id),
                    title=version.title,
                    body_md=version.body_md[:CLASSIFIER_EXAMPLE_BODY_MAX_CHARACTERS],
                    labels=labels,
                    is_gold=False,
                )
            )
        return examples

    async def eligible_count(self, *, limit: int) -> int:
        limited = self._eligible_query().with_only_columns(News.id).limit(limit).subquery()
        return int(await self.session.scalar(select(func.count()).select_from(limited)) or 0)

    @staticmethod
    def _eligible_query():
        latest = (
            select(
                ManualLabelDecision.news_id,
                ManualLabelDecision.version_id,
                ManualLabelDecision.facet_id,
                func.max(ManualLabelDecision.revision).label("revision"),
            )
            .where(ManualLabelDecision.origin == "manual")
            .group_by(
                ManualLabelDecision.news_id,
                ManualLabelDecision.version_id,
                ManualLabelDecision.facet_id,
            )
            .subquery()
        )
        active = (
            select(ManualLabelDecision.news_id)
            .join(
                latest,
                (latest.c.news_id == ManualLabelDecision.news_id)
                & (latest.c.version_id == ManualLabelDecision.version_id)
                & (latest.c.facet_id == ManualLabelDecision.facet_id)
                & (latest.c.revision == ManualLabelDecision.revision),
            )
            .where(
                ManualLabelDecision.action == "set",
                ManualLabelDecision.news_id == News.id,
                ManualLabelDecision.version_id == News.current_version_id,
            )
            .correlate(News)
            .exists()
        )
        skip_classification = (
            select(NewsSourceLink.news_id)
            .join(Submission, Submission.id == NewsSourceLink.submission_id)
            .join(Source, Source.id == Submission.source_id)
            .where(
                NewsSourceLink.news_id == News.id,
                Source.skip_classification.is_(True),
            )
            .exists()
        )
        return (
            select(News, NewsVersion)
            .join(NewsVersion, News.current_version_id == NewsVersion.id)
            .where(
                News.status == "published",
                News.is_gold.is_(False),
                active,
                ~skip_classification,
            )
        )

    async def _latest_labels(
        self,
        news_id: uuid.UUID,
        version_id: uuid.UUID,
        allowed_axes: set[str],
    ) -> dict[str, list[str]]:
        decisions = (
            await self.session.execute(
                select(ManualLabelDecision, Facet)
                .join(Facet, Facet.id == ManualLabelDecision.facet_id)
                .where(
                    ManualLabelDecision.news_id == news_id,
                    ManualLabelDecision.version_id == version_id,
                    ManualLabelDecision.origin == "manual",
                    Facet.enabled.is_(True),
                    Facet.slug.in_(allowed_axes),
                )
                .order_by(ManualLabelDecision.revision.desc())
            )
        ).all()
        latest: dict[uuid.UUID, tuple[ManualLabelDecision, Facet]] = {}
        for decision, facet in decisions:
            latest.setdefault(facet.id, (decision, facet))
        labels: dict[str, list[str]] = {}
        for decision, facet in latest.values():
            if decision.action != "set":
                continue
            labels[facet.slug] = list(
                await self.session.scalars(
                    select(FacetValue.slug)
                    .join(NewsLabel, NewsLabel.value_id == FacetValue.id)
                    .where(
                        NewsLabel.origin == "manual",
                        NewsLabel.origin_key == str(decision.id),
                        FacetValue.enabled.is_(True),
                    )
                    .order_by(FacetValue.slug)
                )
            )
        return labels
