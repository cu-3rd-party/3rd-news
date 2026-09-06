from __future__ import annotations

import uuid
from typing import Any

from lib.infra.storage.postgres.models import Facet, ManualLabelDecision, News, NewsLabel
from lib.interactor.errors import ValidationError
from sqlalchemy import select

from .resolver import LabelResolver


class ManualLabelDecisions:
    async def replace(
        self,
        session: Any,
        news: News,
        labels: dict[str, list[str]],
        user_id: uuid.UUID | None,
    ) -> None:
        facets = await LabelResolver().resolve(session, labels)
        for facet, values in facets.values():
            decision = await self.append(session, news, facet, action="set", user_id=user_id)
            for value in values:
                session.add(
                    NewsLabel(
                        news_id=news.id,
                        version_id=news.current_version_id,
                        facet_id=facet.id,
                        value_id=value.id,
                        origin="manual",
                        origin_key=str(decision.id),
                        created_by_user_id=user_id,
                    )
                )

    async def release(
        self,
        session: Any,
        news: News,
        facet_slugs: list[str],
        user_id: uuid.UUID | None = None,
    ) -> None:
        if not facet_slugs:
            return
        facets = (
            await session.scalars(select(Facet).where(Facet.slug.in_(set(facet_slugs))))
        ).all()
        if len(facets) != len(set(facet_slugs)):
            raise ValidationError("unknown facet in release list")
        for facet in facets:
            await self.append(session, news, facet, action="release", user_id=user_id)

    async def append(
        self,
        session: Any,
        news: News,
        facet: Facet,
        *,
        action: str,
        user_id: uuid.UUID | None,
    ) -> ManualLabelDecision:
        if news.current_version_id is None:
            raise ValidationError("news has no current version")
        current = await session.scalar(
            select(ManualLabelDecision.revision)
            .where(
                ManualLabelDecision.news_id == news.id,
                ManualLabelDecision.version_id == news.current_version_id,
                ManualLabelDecision.facet_id == facet.id,
            )
            .order_by(ManualLabelDecision.revision.desc())
            .limit(1)
        )
        decision = ManualLabelDecision(
            news_id=news.id,
            version_id=news.current_version_id,
            facet_id=facet.id,
            revision=int(current or 0) + 1,
            origin="manual",
            action=action,
            created_by_user_id=user_id,
        )
        session.add(decision)
        await session.flush()
        return decision

    async def latest(
        self, session: Any, news_id: uuid.UUID, version_id: uuid.UUID | None
    ) -> dict[str, ManualLabelDecision]:
        rows = (
            await session.execute(
                select(ManualLabelDecision, Facet)
                .join(Facet, Facet.id == ManualLabelDecision.facet_id)
                .where(
                    ManualLabelDecision.news_id == news_id,
                    ManualLabelDecision.version_id == version_id,
                    ManualLabelDecision.origin == "manual",
                    Facet.enabled.is_(True),
                )
                .order_by(ManualLabelDecision.revision.desc(), ManualLabelDecision.id.desc())
            )
        ).all()
        result: dict[str, ManualLabelDecision] = {}
        for decision, facet in rows:
            result.setdefault(facet.slug, decision)
        return result
