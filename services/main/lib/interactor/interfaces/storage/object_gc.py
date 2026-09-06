from typing import Protocol


class ObjectGarbageCollectionStorage(Protocol):
    async def collect(self) -> int: ...
