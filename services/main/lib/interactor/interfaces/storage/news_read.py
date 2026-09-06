from typing import Any, Protocol


class NewsReadStorage(Protocol):
    async def serialize(self, news: Any, *, admin: bool = False) -> dict[str, Any]: ...
