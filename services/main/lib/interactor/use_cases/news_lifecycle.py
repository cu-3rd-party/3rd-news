from typing import Any

from lib.interactor.interfaces.storage.news_lifecycle import NewsLifecycleStorage


class NewsLifecycle:
    def __init__(self, storage: NewsLifecycleStorage) -> None:
        self.storage = storage

    async def get(self, session: Any, news_id: Any, *, lock: bool = False) -> Any:
        return await self.storage.get(session, news_id, lock=lock)

    async def edit(self, session: Any, news: Any, changes: dict[str, Any], actor: str) -> Any:
        return await self.storage.edit(session, news, changes, actor)

    async def transition(self, session: Any, news: Any, target: Any, actor: str) -> None:
        await self.storage.transition(session, news, target, actor)

    async def reprocess(self, session: Any, news: Any, actor: str) -> Any:
        return await self.storage.reprocess(session, news, actor)
