from typing import Any

from lib.interactor.interfaces.storage.news_merge import NewsMergeStorage


class NewsMerge:
    def __init__(self, storage: NewsMergeStorage) -> None:
        self.storage = storage

    async def get(self, session: Any, news_id: Any, *, lock: bool = False) -> Any:
        return await self.storage.get(session, news_id, lock=lock)

    async def merge(self, session: Any, target: Any, source_ids: list[Any], actor: str) -> None:
        await self.storage.merge(session, target, source_ids, actor)
