from __future__ import annotations

from collections.abc import AsyncIterable, Mapping, Sequence
from typing import Any, Protocol

from lib.dto.index_task import IndexTask


class SearchClient(Protocol):
    async def search(
        self,
        query: str,
        *,
        filters: str | Sequence[str] | None = None,
        facets: Sequence[str] = (),
        sort: Sequence[str] = (),
        offset: int = 0,
        limit: int = 20,
    ) -> Mapping[str, Any]: ...

    async def ready(self) -> None: ...

    async def close(self) -> None: ...

    async def put_documents(
        self, documents: Sequence[Mapping[str, Any]], *, uid: str | None = None
    ) -> int: ...

    async def delete_documents(self, ids: Sequence[str], *, uid: str | None = None) -> int: ...

    async def wait_task(
        self, task_uid: int, *, timeout_seconds: float | None = None
    ) -> IndexTask: ...

    async def replace_all(
        self,
        documents: Sequence[Mapping[str, Any]] | AsyncIterable[Mapping[str, Any]],
        *,
        batch_size: int = 500,
        filterable: Sequence[str] = (),
        sortable: Sequence[str] = (),
        searchable: Sequence[str] = ("title", "body", "source_text"),
    ) -> int: ...
