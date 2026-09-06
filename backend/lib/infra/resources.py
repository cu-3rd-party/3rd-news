import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Self, cast

import asyncpg
import coredis
from meilisearch_python_sdk import AsyncClient as SearchClient

from lib.core.config import Settings

logger = logging.getLogger(__name__)


class ResourceName(StrEnum):
    DB = auto()
    CACHE = auto()
    SEARCH = auto()


ResourceStatus = dict[str, bool]


@dataclass(slots=True)
class AppResources:
    db: asyncpg.Pool
    cache: coredis.Redis[bytes]
    search: SearchClient
    healthcheck_timeout: float
    _closed: bool = field(default=False, init=False)

    @classmethod
    def initial_status(cls) -> ResourceStatus:
        return {name.value: False for name in ResourceName}

    @classmethod
    async def create(cls, settings: Settings) -> Self:
        async with AsyncExitStack() as stack:
            db = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_max_size,
                command_timeout=settings.db_command_timeout,
                statement_cache_size=settings.db_statement_cache_size,
                server_settings={"application_name": settings.project_name},
            )
            stack.push_async_callback(db.close)

            cache: coredis.Redis[bytes] = coredis.Redis.from_url(
                settings.cache_url,
                decode_responses=False,
                verify_version=False,
                max_connections=settings.cache_pool_max_connections,
                connect_timeout=settings.cache_connect_timeout,
                stream_timeout=settings.cache_command_timeout,
            )
            stack.callback(cache.connection_pool.disconnect)

            search = SearchClient(
                settings.search_engine_url,
                settings.search_engine_master_key_value,
                timeout=int(settings.search_engine_timeout),
            )
            stack.push_async_callback(search.aclose)

            resources = cls(
                db=db,
                cache=cache,
                search=search,
                healthcheck_timeout=settings.resources_healthcheck_timeout,
            )

            status = await resources.status()
            failed = [name for name, ready in status.items() if not ready]

            if failed:
                raise RuntimeError(f"Resources not ready: {', '.join(failed)}")

            stack.pop_all()
            return resources

    async def close(self) -> None:
        if self._closed:
            return

        self._closed = True

        try:
            await self.db.close()
        except Exception:
            logger.exception("Error closing <db>")

        try:
            self.cache.connection_pool.disconnect()
        except Exception:
            logger.exception("Error closing <cache>")

        try:
            await self.search.aclose()
        except Exception:
            logger.exception("Error closing <search client>")

    async def status(self) -> ResourceStatus:
        async with asyncio.TaskGroup() as tg:
            db_task = tg.create_task(self._check_db())
            cache_task = tg.create_task(self._check_cache())
            search_task = tg.create_task(self._check_search())

        return {
            ResourceName.DB.value: db_task.result(),
            ResourceName.CACHE.value: cache_task.result(),
            ResourceName.SEARCH.value: search_task.result(),
        }

    async def _check_db(self) -> bool:
        try:
            async with asyncio.timeout(self.healthcheck_timeout):
                async with self.db.acquire() as connection:
                    result = cast("int | None", await connection.fetchval("select 1"))
                    return result == 1
        except Exception:
            logger.exception("Check db failed")
            return False

    async def _check_cache(self) -> bool:
        try:
            async with asyncio.timeout(self.healthcheck_timeout):
                cache_ping = await self.cache.ping()
                return cache_ping is True or cache_ping in {b"PONG", "PONG"}
        except Exception:
            logger.exception("Check cache failed")
            return False

    async def _check_search(self) -> bool:
        try:
            async with asyncio.timeout(self.healthcheck_timeout):
                search_health = await self.search.health()
                return search_health.status == "available"
        except Exception:
            logger.exception("Check search failed")
            return False
