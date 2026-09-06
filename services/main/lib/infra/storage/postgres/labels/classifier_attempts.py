from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from lib.infra.storage.postgres.models import Classifier, ProcessingAttempt
from sqlalchemy import select


class ClassifierAttempts:
    async def latest(
        self,
        session: Any,
        news_id: uuid.UUID,
        version_id: uuid.UUID | None,
        classifiers: Iterable[Classifier],
    ) -> dict[str, str]:
        slug_by_id = {item.id: item.slug for item in classifiers}
        attempts = (
            await session.scalars(
                select(ProcessingAttempt)
                .where(
                    ProcessingAttempt.news_id == news_id,
                    ProcessingAttempt.version_id == version_id,
                    ProcessingAttempt.classifier_id.is_not(None),
                    ProcessingAttempt.status == "succeeded",
                )
                .order_by(
                    ProcessingAttempt.completed_at.desc().nullslast(),
                    ProcessingAttempt.started_at.desc(),
                    ProcessingAttempt.id.desc(),
                )
            )
        ).all()
        result: dict[str, str] = {}
        for attempt in attempts:
            slug = slug_by_id.get(attempt.classifier_id)
            if slug is not None and slug not in result:
                result[slug] = str(attempt.id)
        return result
