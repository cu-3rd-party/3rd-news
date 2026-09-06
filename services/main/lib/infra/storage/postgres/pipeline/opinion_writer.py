from __future__ import annotations

from typing import Any

from lib.domain import AxisDefinition, NormalizedLabel
from lib.infra.storage.postgres.labels import SqlAlchemyLabelStorage
from lib.infra.storage.postgres.models import (
    Classifier,
    Facet,
    FacetValue,
    News,
    NewsLabel,
    ProcessingAttempt,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class PipelineOpinionWriter:
    async def append(
        self,
        session: AsyncSession,
        news: News,
        attempt: ProcessingAttempt,
        classifier: Classifier,
        labels: tuple[NormalizedLabel, ...],
        axes: dict[str, AxisDefinition],
    ) -> None:
        if not labels:
            return
        facet_rows = (
            await session.scalars(select(Facet).where(Facet.slug.in_({x.axis for x in labels})))
        ).all()
        facets = {row.slug: row for row in facet_rows}
        values = (
            await session.scalars(
                select(FacetValue).where(
                    FacetValue.facet_id.in_([row.id for row in facet_rows]),
                    FacetValue.slug.in_({x.value for x in labels}),
                )
            )
        ).all()
        value_map = {(row.facet_id, row.slug): row for row in values}
        for label in labels:
            facet = facets.get(label.axis)
            value = value_map.get((facet.id, label.value)) if facet else None
            if facet is None or value is None or label.value not in axes[label.axis].values:
                continue
            session.add(
                NewsLabel(
                    news_id=news.id,
                    version_id=attempt.version_id,
                    facet_id=facet.id,
                    value_id=value.id,
                    origin="shadow" if classifier.shadow else "classifier",
                    origin_key=f"{classifier.slug}:{attempt.id}",
                    confidence=label.confidence,
                    reason=label.reason,
                    evidence={"items": list(label.evidence), "attempt_id": str(attempt.id)},
                )
            )

    async def materialize(self, session: AsyncSession, news: News) -> None:
        await SqlAlchemyLabelStorage().recompute(session, news)

    def label_json(self, label: NormalizedLabel) -> dict[str, Any]:
        return {
            "axis": label.axis,
            "value": label.value,
            "confidence": label.confidence,
            "reason": label.reason,
            "evidence": list(label.evidence),
        }
