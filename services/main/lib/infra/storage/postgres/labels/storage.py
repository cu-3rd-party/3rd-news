from __future__ import annotations

from typing import Any

from lib.interactor.interfaces.storage.labels import LabelStorage

from .manual_labels import ManualLabels
from .materializer import LabelMaterializer
from .recorder import LabelRecorder


class SqlAlchemyLabelStorage(LabelStorage):
    async def record(
        self,
        session: Any,
        news: Any,
        labels: dict[str, list[str]],
        *,
        origin: str,
        origin_key: str,
    ) -> None:
        await LabelRecorder().record(session, news, labels, origin=origin, origin_key=origin_key)

    async def set_manual(
        self, session: Any, news: Any, labels: dict[str, list[str]], user_id: Any
    ) -> None:
        await ManualLabels().set(session, news, labels, user_id)

    async def apply_manual(
        self,
        session: Any,
        news: Any,
        labels: dict[str, list[str]],
        release_facets: list[str],
        user_id: Any,
    ) -> None:
        await ManualLabels().apply(session, news, labels, release_facets, user_id)

    async def release(self, session: Any, news: Any, facet_slugs: list[str]) -> None:
        await ManualLabels().release(session, news, facet_slugs)

    async def recompute(self, session: Any, news: Any) -> None:
        await LabelMaterializer().recompute(session, news)
