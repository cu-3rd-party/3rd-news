import asyncio

from lib.interactor.interfaces.storage.object_gc import ObjectGarbageCollectionStorage


class ObjectGarbageCollector:
    def __init__(
        self, storage: ObjectGarbageCollectionStorage, *, interval_seconds: float = 3600
    ) -> None:
        self.storage = storage
        self.interval_seconds = interval_seconds

    async def run(self, *, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.collect()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass

    async def collect(self) -> int:
        return await self.storage.collect()
