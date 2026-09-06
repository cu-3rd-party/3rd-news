import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from ..core.config import Settings
from ..domain.entities.channel_ref import ChannelRef
from ..domain.entities.poll_policy import PollPolicy
from ..domain.entities.selection import Selection
from ..interactor.errors.logical import ParserConfigurationError
from ..interactor.interfaces.clients.parser_application import ParserApplication
from ..interactor.use_cases.channel_catalog import ChannelCatalog
from ..interactor.use_cases.poll_selections import PollSelections
from ..interactor.use_cases.post_conversion import parse_channels
from .clients.ingest import NewsIngestClient
from .clients.time import TimeClient
from .storage.json_selection import JsonSelectionStorage

logger = logging.getLogger("thirdnews.parser.time.lifecycle")


@dataclass(slots=True)
class AppResources(ParserApplication):
    settings: Settings
    storage: JsonSelectionStorage
    catalog: ChannelCatalog
    poll_use_case: PollSelections
    poll_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    background: asyncio.Task[None] | None = None

    @classmethod
    async def create(cls, settings: Settings) -> AppResources:
        storage = JsonSelectionStorage(settings.state_path)
        storage.seed(
            [
                Selection(team=ref.team, channel=ref.channel)
                for ref in parse_channels(settings.time_channels)
            ]
        )
        policy = PollPolicy(
            max_age_days=settings.max_age_days,
            posts_per_page=settings.time_posts_per_page,
            max_pages=settings.time_max_pages,
            include_replies=settings.time_include_replies,
            authors=settings.time_authors,
            download_attachments=settings.time_download_attachments,
            max_attachment_bytes=settings.time_max_attachment_bytes,
        )
        catalog = ChannelCatalog(settings.channel_cache_ttl_s)
        resources = cls(
            settings=settings,
            storage=storage,
            catalog=catalog,
            poll_use_case=PollSelections(storage, catalog, policy),
        )
        resources.background = asyncio.create_task(resources.run_background())
        return resources

    def time_client(self) -> TimeClient:
        cookie = self.settings.time_cookie.get_secret_value()
        csrf = self.settings.time_csrf.get_secret_value()
        token = self.settings.time_token.get_secret_value()
        if not cookie and not token:
            raise ParserConfigurationError("нет доступа к TiMe: задай TIME_COOKIE или TIME_TOKEN")
        return TimeClient(
            base_url=self.settings.time_base_url,
            cookie=cookie or None,
            csrf=csrf or None,
            token=token or None,
        )

    async def list_teams(self) -> list[dict[str, Any]]:
        async with self.time_client() as client:
            return await client.list_teams()

    async def list_channels(self, refresh: bool = False) -> list[dict[str, Any]]:
        async with self.time_client() as client:
            return await self.catalog.fetch(client, refresh=refresh)

    def selections(self) -> JsonSelectionStorage:
        return self.storage

    def channel_url(self, team: str, channel: str) -> str:
        return f"{self.settings.time_base_url}/{team}/channels/{channel}"

    def status_details(self) -> dict[str, Any]:
        return {
            "time_base_url": self.settings.time_base_url,
            "authorized": bool(
                self.settings.time_cookie.get_secret_value()
                or self.settings.time_token.get_secret_value()
            ),
            "news_url": self.settings.news_url,
            "news_key_configured": bool(self.settings.news_api_key.get_secret_value()),
            "poll_interval_s": self.settings.poll_interval_s,
            "selected": len(self.storage.selected()),
            "last_runs": self.storage.runs(),
        }

    async def poll(
        self,
        only: ChannelRef | None = None,
        max_age_days: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        api_key = self.settings.news_api_key.get_secret_value()
        if not api_key:
            raise ParserConfigurationError("не задан NEWS_API_KEY")
        async with self.poll_lock, aiohttp.ClientSession() as session:
            ingest = NewsIngestClient(self.settings.news_url, api_key, session)
            async with self.time_client() as time_client:
                return await self.poll_use_case.execute(
                    time_client,
                    ingest,
                    only=only,
                    max_age_days=max_age_days,
                    max_pages=max_pages,
                )

    async def run_background(self) -> None:
        while True:
            await asyncio.sleep(self.settings.poll_interval_s)
            try:
                await self.poll()
            except Exception:
                logger.exception("background poll failed")
                continue

    async def close(self) -> None:
        if self.background is not None:
            self.background.cancel()
            await asyncio.gather(self.background, return_exceptions=True)
            self.background = None
