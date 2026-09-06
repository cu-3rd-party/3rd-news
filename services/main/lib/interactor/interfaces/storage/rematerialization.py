from typing import Protocol


class RematerializationStorage(Protocol):
    async def process_one(self) -> bool: ...
