from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Self

from lib.core.config import Settings
from lib.infra.clients.auth import AuthService
from lib.infra.clients.search import MeiliSearchClient
from lib.infra.storage.postgres.database import Database
from lib.infra.storage.s3 import S3ObjectStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppResources:
    database: Any
    search: Any
    storage: Any
    auth: AuthService
    timeout_seconds: float
    owned: tuple[Any, ...]

    @classmethod
    def initial_status(cls) -> dict[str, bool]:
        return {"database": False, "search": False, "storage": False}

    @classmethod
    async def create(
        cls,
        settings: Settings,
        *,
        database=None,
        search=None,
        storage=None,
        auth=None,
    ) -> Self:
        owned = []
        try:
            if database is None:
                database = Database(settings.db_url)
                owned.append(database)
            if search is None:
                search = MeiliSearchClient(
                    settings.search_url,
                    settings.search_key_value,
                    index=settings.search_index,
                    timeout_seconds=settings.search_task_timeout_seconds,
                )
                owned.append(search)
            if storage is None:
                storage = S3ObjectStore(
                    endpoint_url=settings.file_endpoint,
                    public_endpoint_url=settings.file_public_endpoint,
                    bucket=settings.file_bucket,
                    access_key=settings.file_access_key_value,
                    secret_key=settings.file_secret_key_value,
                    region=settings.file_region,
                    presign_ttl_seconds=settings.file_presign_ttl_seconds,
                    max_upload_bytes=settings.upload_max_bytes,
                )
                owned.append(storage)
            if auth is None:
                auth = AuthService(
                    private_key=settings.auth_private_key,
                    public_key=settings.auth_public_key,
                    password_verify_concurrency=settings.auth_password_verify_concurrency,
                    password_verify_queue_size=settings.auth_password_verify_queue_size,
                )
            auth.bind_database(
                database.session_factory,
                api_key_touch_interval_seconds=settings.auth_api_key_touch_interval_seconds,
            )
            await auth.resolve_trusted_proxy_hosts(
                settings.auth_trusted_proxy_hosts,
                timeout_seconds=settings.healthcheck_timeout_seconds,
            )
            return cls(
                database, search, storage, auth, settings.healthcheck_timeout_seconds, tuple(owned)
            )
        except BaseException:
            for resource in reversed(owned):
                await resource.close()
            raise

    async def status(self) -> dict[str, bool]:
        checks = {"database": False, "search": False, "storage": False}

        async def check(name: str, resource: Any) -> None:
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    await resource.ready()
                checks[name] = True
            except Exception:
                logger.warning("Readiness check failed dependency=%s", name, exc_info=True)

        async with asyncio.TaskGroup() as group:
            group.create_task(check("database", self.database))
            group.create_task(check("search", self.search))
            group.create_task(check("storage", self.storage))
        return checks

    async def close(self) -> None:
        for resource in reversed(self.owned):
            close = getattr(resource, "close", None)
            if close:
                try:
                    await close()
                except Exception:
                    logger.exception("Could not close resource type=%s", type(resource).__name__)
