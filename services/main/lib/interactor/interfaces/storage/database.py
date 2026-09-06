from collections.abc import AsyncIterator
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DatabaseGateway(Protocol):
    session_factory: async_sessionmaker[AsyncSession]

    def session(self) -> AsyncIterator[AsyncSession]: ...

    async def ready(self) -> None: ...

    async def close(self) -> None: ...
