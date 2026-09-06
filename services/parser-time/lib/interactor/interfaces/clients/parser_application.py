from abc import ABC, abstractmethod
from typing import Any

from ....domain.entities.channel_ref import ChannelRef
from ..storage.selection import SelectionStorage


class ParserApplication(ABC):
    @abstractmethod
    async def list_teams(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def list_channels(self, refresh: bool = False) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def selections(self) -> SelectionStorage:
        raise NotImplementedError

    @abstractmethod
    def channel_url(self, team: str, channel: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def status_details(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def poll(
        self,
        only: ChannelRef | None = None,
        max_age_days: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        raise NotImplementedError
