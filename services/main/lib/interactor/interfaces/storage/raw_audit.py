from typing import Any, Protocol


class RawAuditStorage(Protocol):
    async def read(self, *args: Any, **values: Any) -> Any: ...
