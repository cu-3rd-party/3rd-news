import asyncio

from lib.interactor.interfaces.storage.pipeline_coordinator import PipelineCoordinatorStorage


class PipelineCoordinator:
    def __init__(self, storage: PipelineCoordinatorStorage, *, poll_seconds: float) -> None:
        self.storage = storage
        self.poll_seconds = poll_seconds

    async def run(self, *, stop: asyncio.Event) -> None:
        while not stop.is_set():
            if await self.advance_one():
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                pass

    async def advance_one(self) -> bool:
        return await self.storage.advance_one()
