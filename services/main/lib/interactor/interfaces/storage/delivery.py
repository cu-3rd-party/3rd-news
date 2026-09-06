from typing import Any, Protocol


class DeliveryStorage(Protocol):
    async def pending(self, limit: int) -> list[dict[str, object]]: ...

    async def replay(self, *args: Any, **values: Any) -> Any: ...
