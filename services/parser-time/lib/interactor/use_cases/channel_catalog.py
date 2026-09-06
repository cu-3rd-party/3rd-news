import asyncio
import time
from typing import Any

from ..interfaces.clients.time import TimeGateway


class ChannelCatalog:
    def __init__(self, cache_ttl_s: int) -> None:
        self._cache_ttl_s = cache_ttl_s
        self._cached_at = 0.0
        self._channels: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def fetch(self, client: TimeGateway, refresh: bool = False) -> list[dict[str, Any]]:
        async with self._lock:
            if self._channels and not refresh and time.time() - self._cached_at < self._cache_ttl_s:
                return self._channels
        collected: list[dict[str, Any]] = []
        for team in await client.list_teams():
            joined = {channel["id"] for channel in await client.list_joined_channels(team["id"])}
            for channel in await client.list_public_channels(team["id"]):
                if channel.get("delete_at"):
                    continue
                item = dict(channel)
                item["_team_name"] = team["name"]
                item["_joined"] = channel["id"] in joined
                collected.append(item)
        async with self._lock:
            self._cached_at = time.time()
            self._channels = collected
        return collected
