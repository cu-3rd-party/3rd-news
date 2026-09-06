from typing import Any

from lib.interactor.interfaces.storage.news_split import NewsSplitStorage


class NewsSplit:
    def __init__(self, storage: NewsSplitStorage) -> None:
        self.storage = storage

    async def get(self, session: Any, news_id: Any, *, lock: bool = False) -> Any:
        return await self.storage.get(session, news_id, lock=lock)

    async def split(self, session: Any, news: Any, submission_ids: list[Any], actor: str) -> Any:
        return await self.storage.split(session, news, submission_ids, actor)
