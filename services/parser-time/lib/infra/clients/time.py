import logging
from typing import Any, Self

import aiohttp

from ...domain.entities.channel_ref import ChannelRef
from ...domain.entities.post_rules import NEWS_CHANNEL_TYPES
from ...interactor.errors.time_api import TimeApiError
from ...interactor.errors.time_auth import TimeAuthError
from ...interactor.interfaces.clients.time import TimeGateway

logger = logging.getLogger("thirdnews.parser.time")


class TimeClient(TimeGateway):
    def __init__(
        self,
        base_url: str = "https://time.cu.ru",
        cookie: str | None = None,
        csrf: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not cookie and not token:
            raise TimeAuthError("нужен либо TIME_COOKIE, либо TIME_TOKEN")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "3rd-news-time-parser/2.0",
        }
        if cookie:
            self.headers["Cookie"] = cookie
        if csrf:
            self.headers["X-CSRF-Token"] = csrf
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> Self:
        self._session = aiohttp.ClientSession(
            base_url=f"{self.base_url}/api/v4",
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def http(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("TimeClient must be used with async with")
        return self._session

    async def get_json(self, path: str, **params: Any) -> Any:
        async with self.http().get(path, params=params or None) as response:
            text = await response.text()
            if response.status in {401, 403}:
                raise TimeAuthError(f"TiMe отвечает {response.status}; обнови доступ")
            if response.status >= 400:
                raise TimeApiError(f"TiMe отвечает {response.status}: {text[:300]}")
            return await response.json(content_type=None)

    async def whoami(self) -> dict[str, Any]:
        return await self.get_json("/users/me")

    async def resolve_channel(self, ref: ChannelRef) -> dict[str, Any]:
        team = await self.get_json(f"/teams/name/{ref.team}")
        channel = await self.get_json(f"/teams/{team['id']}/channels/name/{ref.channel}")
        channel["team"] = team
        return channel

    async def list_teams(self) -> list[dict[str, Any]]:
        return await self.get_json("/users/me/teams")

    async def list_public_channels(
        self, team_id: str, per_page: int = 200, max_pages: int = 50
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for page in range(max_pages):
            batch = await self.get_json(f"/teams/{team_id}/channels", page=page, per_page=per_page)
            collected.extend(batch)
            if len(batch) < per_page:
                break
        return [item for item in collected if item.get("type") in NEWS_CHANNEL_TYPES]

    async def list_joined_channels(self, team_id: str) -> list[dict[str, Any]]:
        channels = await self.get_json(f"/users/me/teams/{team_id}/channels")
        return [item for item in channels if item.get("type") in NEWS_CHANNEL_TYPES]

    async def channel_member_roles(self, channel_id: str, user_id: str) -> set[str]:
        try:
            member = await self.get_json(f"/channels/{channel_id}/members/{user_id}")
        except TimeApiError:
            return set()
        return set((member.get("roles") or "").split())

    async def fetch_posts(
        self, channel_id: str, per_page: int = 60, max_pages: int = 5
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for page in range(max_pages):
            payload = await self.get_json(
                f"/channels/{channel_id}/posts", page=page, per_page=per_page
            )
            order = payload.get("order") or []
            posts = payload.get("posts") or {}
            collected.extend(posts[post_id] for post_id in order if post_id in posts)
            if len(order) < per_page:
                break
        return collected

    async def download_file(self, file_id: str, max_bytes: int) -> bytes | None:
        async with self.http().get(f"/files/{file_id}") as response:
            if response.status >= 400:
                logger.warning("не смог скачать файл %s: %s", file_id, response.status)
                return None
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.content.iter_chunked(64 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    logger.warning("файл %s больше лимита", file_id)
                    return None
                chunks.append(chunk)
            return b"".join(chunks)

    async def user_display_name(self, user_id: str) -> str | None:
        try:
            user = await self.get_json(f"/users/{user_id}")
        except TimeApiError, TimeAuthError:
            return None
        full = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        return full or user.get("username")
