from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from lib.dto.incoming_message import IncomingMessage
from lib.infra.storage.postgres.models import InboxMessage
from lib.interactor.interfaces.clients.inbox import InboxClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

InboxCallback = Callable[[AsyncSession, Mapping[str, Any]], Awaitable[None]]


class DatabaseInboxHandler(InboxClient):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        consumer_name: str,
        callback: InboxCallback,
    ) -> None:
        self.sessions = session_factory
        self.consumer_name = consumer_name
        self.callback = callback

    async def __call__(self, message: IncomingMessage) -> None:
        async with self.sessions() as session:
            marker = InboxMessage(
                consumer_name=self.consumer_name,
                message_id=message.id,
            )
            session.add(marker)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                return
            try:
                await self.callback(session, message.payload)
                marker.processed_at = datetime.now(UTC)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
