from __future__ import annotations

from typing import Any, Protocol


class LabelStorage(Protocol):
    async def record(
        self,
        session: Any,
        news: Any,
        labels: dict[str, list[str]],
        *,
        origin: str,
        origin_key: str,
    ) -> None: ...

    async def set_manual(
        self, session: Any, news: Any, labels: dict[str, list[str]], user_id: Any
    ) -> None: ...

    async def apply_manual(
        self,
        session: Any,
        news: Any,
        labels: dict[str, list[str]],
        release_facets: list[str],
        user_id: Any,
    ) -> None: ...

    async def release(self, session: Any, news: Any, facet_slugs: list[str]) -> None: ...

    async def recompute(self, session: Any, news: Any) -> None: ...
