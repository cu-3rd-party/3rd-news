import asyncio

from lib.interactor.interfaces.storage.rematerialization import RematerializationStorage


class RematerializationWorker:
    def __init__(self, storage: RematerializationStorage, *, poll_seconds: float) -> None:
        self.storage = storage
        self.poll_seconds = poll_seconds

    async def run(self, *, stop: asyncio.Event) -> None:
        while not stop.is_set():
            if await self.process_one():
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                pass

    async def process_one(self) -> bool:
        return await self.storage.process_one()
