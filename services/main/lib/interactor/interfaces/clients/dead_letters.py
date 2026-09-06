from typing import Any, Protocol


class DeadLetterClient(Protocol):
    async def list(self, *, after: int, limit: int) -> dict[str, Any]: ...
