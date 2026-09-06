from collections.abc import Mapping
from typing import Any, Protocol, Self


class BrokerClient(Protocol):
    @property
    def jetstream(self) -> Any: ...

    async def connect(self) -> Self: ...

    async def close(self) -> None: ...

    async def publish_json(
        self,
        subject: str,
        payload: Mapping[str, Any],
        *,
        message_id: str,
    ) -> Any: ...
