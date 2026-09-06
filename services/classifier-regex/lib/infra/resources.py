import asyncio
from dataclasses import dataclass, field


@dataclass(slots=True)
class AppResources:
    background: set[asyncio.Task[None]] = field(default_factory=set)

    @classmethod
    async def create(cls) -> AppResources:
        return cls()

    async def close(self) -> None:
        pending = tuple(self.background)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
