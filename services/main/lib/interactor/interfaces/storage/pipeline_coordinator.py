from typing import Protocol


class PipelineCoordinatorStorage(Protocol):
    async def advance_one(self) -> bool: ...
