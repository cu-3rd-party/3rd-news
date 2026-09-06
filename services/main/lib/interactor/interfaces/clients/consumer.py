import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from lib.dto.incoming_message import IncomingMessage


class ConsumerClient(Protocol):
    async def run(
        self,
        handler: Callable[[IncomingMessage], Awaitable[None]],
        *,
        stop: asyncio.Event,
    ) -> None: ...
