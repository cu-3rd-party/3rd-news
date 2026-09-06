from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from lib.core.config import (
    OBJECT_GC_BATCH_SIZE,
    OBJECT_GC_GRACE_HOURS,
    OBJECT_GC_INTERVAL_SECONDS,
    UPLOAD_UNUSED_RETENTION_DAYS,
)
from lib.infra.storage.postgres.models import Attachment, UploadIntent
from lib.infra.storage.s3 import S3ObjectStore
from lib.interactor.interfaces.storage.object_gc import ObjectGarbageCollectionStorage
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyObjectGarbageCollectionStorage(ObjectGarbageCollectionStorage):
    def __init__(self, sessions: async_sessionmaker[AsyncSession], storage: S3ObjectStore) -> None:
        self.sessions = sessions
        self.storage = storage

    async def run(self, *, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.collect()
            except Exception as error:
                logging.getLogger(__name__).warning(
                    "object cleanup retry: %s", type(error).__name__
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=OBJECT_GC_INTERVAL_SECONDS)
            except TimeoutError:
                pass

    async def collect(self) -> int:
        now = datetime.now(UTC)
        removed = 0
        async with self.sessions() as session, session.begin():
            intents = await session.scalars(
                select(UploadIntent)
                .where(
                    UploadIntent.attachment_id.is_(None),
                    or_(
                        (UploadIntent.status == "pending") & (UploadIntent.expires_at < now),
                        (UploadIntent.status == "completed")
                        & (
                            UploadIntent.completed_at
                            < now - timedelta(days=UPLOAD_UNUSED_RETENTION_DAYS)
                        ),
                    ),
                )
                .order_by(UploadIntent.expires_at)
                .limit(OBJECT_GC_BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            for intent in intents:
                await self.storage.delete(intent.temp_key)
                if intent.final_key:
                    await self.storage.delete(intent.final_key)
                intent.status = "expired"
                removed += 1

        async for key in self.storage.objects_before(now - timedelta(hours=OBJECT_GC_GRACE_HOURS)):
            if not key.startswith(("tmp/", "objects/")):
                continue
            async with self.sessions() as session:
                attachment = await session.scalar(
                    select(exists().where(Attachment.object_key == key))
                )
                intent = await session.scalar(
                    select(
                        exists().where(
                            or_(
                                (UploadIntent.status == "pending")
                                & (UploadIntent.temp_key == key)
                                & (UploadIntent.expires_at > now),
                                (UploadIntent.status == "completed")
                                & (UploadIntent.final_key == key),
                            ),
                        )
                    )
                )
            if not attachment and not intent:
                await self.storage.delete(key)
                removed += 1
                if removed >= OBJECT_GC_BATCH_SIZE:
                    break
        return removed
