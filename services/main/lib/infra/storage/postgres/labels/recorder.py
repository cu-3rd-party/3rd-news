from __future__ import annotations

from typing import Any

from lib.infra.storage.postgres.models import News, NewsLabel

from .materializer import LabelMaterializer
from .resolver import LabelResolver


class LabelRecorder:
    async def record(
        self,
        session: Any,
        news: News,
        labels: dict[str, list[str]],
        *,
        origin: str,
        origin_key: str,
    ) -> None:
        facets = await LabelResolver().resolve(session, labels)
        for facet, values in facets.values():
            for value in values:
                session.add(
                    NewsLabel(
                        news_id=news.id,
                        version_id=news.current_version_id,
                        facet_id=facet.id,
                        value_id=value.id,
                        origin=origin,
                        origin_key=origin_key,
                    )
                )
        await session.flush()
        await LabelMaterializer().recompute(session, news)
