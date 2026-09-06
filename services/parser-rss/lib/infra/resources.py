import asyncio
from dataclasses import dataclass

from ..core.config import Settings
from ..domain.entities.feed_source import FeedSource
from ..interactor.errors.logical import ParserConfigurationError
from ..interactor.interfaces.storage.health import HealthStorage
from ..interactor.use_cases.parse_feed import parse_feeds
from ..interactor.use_cases.poll_feeds import run_poller
from ..interactor.use_cases.supervise import supervise_poller
from .clients.feed import AiohttpFeedClient
from .clients.ingest import NewsIngestClient
from .storage.memory_health import MemoryHealthStorage


@dataclass(slots=True)
class AppResources:
    health: HealthStorage
    feed_client: AiohttpFeedClient
    ingest_client: NewsIngestClient
    feeds: list[FeedSource]
    poller: asyncio.Task[None] | None = None

    @classmethod
    async def create(cls, settings: Settings) -> AppResources:
        api_key = settings.news_api_key.get_secret_value()
        if not api_key:
            raise ParserConfigurationError("NEWS_API_KEY is required")
        feeds = parse_feeds(settings.feeds)
        if not feeds:
            raise ParserConfigurationError("FEEDS is empty; expected source|url pairs")
        feed_client = AiohttpFeedClient(settings.fetch_timeout_s, settings.max_feed_bytes)
        await feed_client.open()
        resources = cls(
            health=MemoryHealthStorage(),
            feed_client=feed_client,
            ingest_client=NewsIngestClient(settings.news_url, api_key),
            feeds=feeds,
        )

        async def runner() -> None:
            await run_poller(
                resources.feed_client,
                resources.ingest_client,
                resources.feeds,
                settings.max_age_days,
                settings.poll_interval_s,
                resources.health.record_cycle,
            )

        resources.poller = asyncio.create_task(
            supervise_poller(resources.health, runner, settings.retry_delay_s)
        )
        return resources

    async def close(self) -> None:
        if self.poller is not None:
            self.poller.cancel()
            await asyncio.gather(self.poller, return_exceptions=True)
            self.poller = None
        await self.feed_client.close()
