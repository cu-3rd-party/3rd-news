from typing import Any, Protocol


class NewsSplitStorage(Protocol):
    async def get(self, session: Any, news_id: Any, *, lock: bool = False) -> Any: ...

    async def split(
        self, session: Any, news: Any, submission_ids: list[Any], actor: str
    ) -> Any: ...
