from __future__ import annotations

import uuid
from typing import Any

from lib.infra.storage.postgres.models import ManualLabelDecision, News, NewsLabel
from sqlalchemy import select


class NewsProvenance:
    async def copy(self, session: Any, source: News, target: News, operation: str) -> None:
        decisions = (
            await session.scalars(
                select(ManualLabelDecision)
                .where(
                    ManualLabelDecision.news_id == source.id,
                    ManualLabelDecision.version_id == source.current_version_id,
                )
                .order_by(ManualLabelDecision.facet_id, ManualLabelDecision.revision)
            )
        ).all()
        next_revision: dict[uuid.UUID, int] = {}
        for decision in decisions:
            if decision.facet_id not in next_revision:
                current = await session.scalar(
                    select(ManualLabelDecision.revision)
                    .where(
                        ManualLabelDecision.news_id == target.id,
                        ManualLabelDecision.version_id == target.current_version_id,
                        ManualLabelDecision.facet_id == decision.facet_id,
                    )
                    .order_by(ManualLabelDecision.revision.desc())
                    .limit(1)
                )
                next_revision[decision.facet_id] = int(current or 0)
            next_revision[decision.facet_id] += 1
            session.add(
                ManualLabelDecision(
                    news_id=target.id,
                    version_id=target.current_version_id,
                    facet_id=decision.facet_id,
                    revision=next_revision[decision.facet_id],
                    origin="provenance",
                    action=decision.action,
                    evidence={
                        **(decision.evidence or {}),
                        "source_news_id": str(source.id),
                        "source_decision_id": str(decision.id),
                        "operation": operation,
                    },
                    created_by_user_id=decision.created_by_user_id,
                )
            )
        rows = (
            await session.scalars(
                select(NewsLabel).where(
                    NewsLabel.news_id == source.id,
                    NewsLabel.version_id == source.current_version_id,
                )
            )
        ).all()
        for label in rows:
            session.add(
                NewsLabel(
                    news_id=target.id,
                    version_id=target.current_version_id,
                    facet_id=label.facet_id,
                    value_id=label.value_id,
                    origin="provenance",
                    origin_key=f"{operation}:{source.id}:{label.id}",
                    confidence=label.confidence,
                    reason=label.reason,
                    evidence={
                        **(label.evidence or {}),
                        "source_news_id": str(source.id),
                        "source_label_id": str(label.id),
                        "operation": operation,
                    },
                    created_by_user_id=label.created_by_user_id,
                )
            )
