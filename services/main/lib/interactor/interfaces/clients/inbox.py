from typing import Protocol

from lib.dto.incoming_message import IncomingMessage


class InboxClient(Protocol):
    async def __call__(self, message: IncomingMessage) -> None: ...
