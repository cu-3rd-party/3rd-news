import asyncio
from typing import Protocol


class AttachmentProcessingStorage(Protocol):
    async def run(self, *, stop: asyncio.Event, concurrency: int = 2) -> None: ...
