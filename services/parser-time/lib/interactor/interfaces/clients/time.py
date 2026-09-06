from abc import ABC, abstractmethod
from typing import Any

from ....domain.entities.channel_ref import ChannelRef


class TimeGateway(ABC):
    base_url: str

    @abstractmethod
    async def resolve_channel(self, ref: ChannelRef) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def list_teams(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def list_public_channels(self, team_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def list_joined_channels(self, team_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def channel_member_roles(self, channel_id: str, user_id: str) -> set[str]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_posts(
        self, channel_id: str, per_page: int, max_pages: int
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def download_file(self, file_id: str, max_bytes: int) -> bytes | None:
        raise NotImplementedError

    @abstractmethod
    async def user_display_name(self, user_id: str) -> str | None:
        raise NotImplementedError
