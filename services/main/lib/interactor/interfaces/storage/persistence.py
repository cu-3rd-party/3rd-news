from collections.abc import Iterable
from typing import Any, Protocol


class PersistenceStorage(Protocol):
    def add_audit(self, *args: Any, **values: Any) -> None: ...

    async def request_news_projections(self, news_ids: Iterable[Any]) -> None: ...

    def enqueue_news_projection(self, news: Any) -> None: ...
