from typing import Any, Protocol


class NewsMergeStorage(Protocol):
    async def get(self, session: Any, news_id: Any, *, lock: bool = False) -> Any: ...

    async def merge(self, session: Any, target: Any, source_ids: list[Any], actor: str) -> None: ...
