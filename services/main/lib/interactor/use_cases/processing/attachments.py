import asyncio

from lib.interactor.interfaces.storage.attachment_processing import AttachmentProcessingStorage


class AttachmentWorker:
    def __init__(self, storage: AttachmentProcessingStorage) -> None:
        self.storage = storage

    async def run(self, *, stop: asyncio.Event, concurrency: int = 2) -> None:
        await self.storage.run(stop=stop, concurrency=concurrency)
