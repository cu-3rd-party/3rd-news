from __future__ import annotations

from typing import Any

from lib.interactor.interfaces.storage.labels import LabelStorage


class EffectiveLabels:
    def __init__(self, storage: LabelStorage) -> None:
        self.storage = storage

    async def record(
        self,
        session: Any,
        news: Any,
        labels: dict[str, list[str]],
        *,
        origin: str,
        origin_key: str,
    ) -> None:
        await self.storage.record(session, news, labels, origin=origin, origin_key=origin_key)

    async def set_manual(
        self, session: Any, news: Any, labels: dict[str, list[str]], user_id: Any
    ) -> None:
        await self.storage.set_manual(session, news, labels, user_id)

    async def apply_manual(
        self,
        session: Any,
        news: Any,
        labels: dict[str, list[str]],
        release_facets: list[str],
        user_id: Any,
    ) -> None:
        await self.storage.apply_manual(session, news, labels, release_facets, user_id)

    async def release(self, session: Any, news: Any, facet_slugs: list[str]) -> None:
        await self.storage.release(session, news, facet_slugs)

    async def recompute(self, session: Any, news: Any) -> None:
        await self.storage.recompute(session, news)
