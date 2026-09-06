import asyncio
from typing import Protocol


class OutboxClient(Protocol):
    async def run(self, *, stop: asyncio.Event) -> None: ...

    async def publish_batch(self) -> int: ...
