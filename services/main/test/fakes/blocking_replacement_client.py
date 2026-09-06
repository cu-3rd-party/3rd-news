import asyncio


class BlockingReplacementClient:
    index = "qa-reindex"

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.documents: list[dict] = []

    async def replace_all(self, documents, **kwargs) -> int:
        del kwargs
        self.documents = [document async for document in documents]
        self.started.set()
        await self.release.wait()
        return len(self.documents)
