from __future__ import annotations

import uuid
from typing import Any

from lib.infra.storage.postgres.models import News
from lib.interactor.errors import ValidationError

from .manual_decisions import ManualLabelDecisions
from .materializer import LabelMaterializer


class ManualLabels:
    async def set(
        self,
        session: Any,
        news: News,
        labels: dict[str, list[str]],
        user_id: uuid.UUID | None,
    ) -> None:
        await ManualLabelDecisions().replace(session, news, labels, user_id)
        await session.flush()
        await LabelMaterializer().recompute(session, news)

    async def apply(
        self,
        session: Any,
        news: News,
        labels: dict[str, list[str]],
        release_facets: list[str],
        user_id: uuid.UUID | None,
    ) -> None:
        overlap = set(labels) & set(release_facets)
        if overlap:
            raise ValidationError(f"facet cannot be set and released together: {sorted(overlap)}")
        decisions = ManualLabelDecisions()
        await decisions.release(session, news, release_facets, user_id)
        await decisions.replace(session, news, labels, user_id)
        await session.flush()
        await LabelMaterializer().recompute(session, news)

    async def release(self, session: Any, news: News, facet_slugs: list[str]) -> None:
        await ManualLabelDecisions().release(session, news, facet_slugs)
        await LabelMaterializer().recompute(session, news)
