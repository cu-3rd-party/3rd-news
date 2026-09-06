from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from lib.infra.clients.search.indexer import SearchIndexer
from lib.infra.storage.postgres.attachment_processing_storage import (
    SqlAlchemyAttachmentProcessingStorage,
)
from lib.infra.storage.postgres.models import Attachment, Job, News, NewsVersion, UploadIntent
from lib.infra.storage.postgres.object_gc_storage import (
    SqlAlchemyObjectGarbageCollectionStorage,
)
from lib.infra.storage.postgres.repositories.ingest_repository import SqlAlchemyIngestRepository
from lib.infra.storage.postgres.repositories.news_read_repository import NewsReadRepository
from lib.interactor.errors import ConflictError
from lib.interactor.use_cases.processing.object_gc import ObjectGarbageCollector

from .fakes.object_store import ObjectStore
from .fakes.synthetic_fetcher import SyntheticFetcher

pytestmark = pytest.mark.integration


async def test_remote_attachment_is_stored_visible_and_indexed(integration_database):
    async with integration_database() as session, session.begin():
        news = News(status="published")
        session.add(news)
        await session.flush()
        version = NewsVersion(news_id=news.id, number=1, body_md="Synthetic news")
        session.add(version)
        await session.flush()
        news.current_version_id = version.id
        attachment = Attachment(
            news_id=news.id, original_url="https://fixture.example/file", filename="remote.txt"
        )
        session.add(attachment)
        await session.flush()
        job = Job(
            kind="attachment",
            news_id=news.id,
            payload={"attachment_id": str(attachment.id)},
            available_at=datetime(1980, 1, 1, tzinfo=UTC),
        )
        session.add(job)
    storage = ObjectStore()
    processing = SqlAlchemyAttachmentProcessingStorage(
        integration_database, cast(Any, SyntheticFetcher()), cast(Any, storage), node_id="qa-remote"
    )
    claim = await processing.claim()
    assert claim is not None and claim.attachment_id == attachment.id
    await processing.process(claim)
    async with integration_database() as session:
        actual = await session.get(Attachment, attachment.id)
        assert actual.status == "stored"
        assert actual.extracted_text == "Synthetic remote attachment"
        current = await session.get(News, news.id)
        detail = await NewsReadRepository(session).serialize(current)
        assert [item["id"] for item in detail["attachments"]] == [str(attachment.id)]
    document = await SearchIndexer(
        integration_database, cast(Any, SimpleNamespace(index="qa")), owner="qa"
    )._document(news.id)
    assert document is not None and document["has_attachments"] is True


async def test_gc_removes_expired_and_orphan_objects_but_keeps_owned(integration_database):
    owner = f"gc-{uuid4()}"
    completed_temp = f"tmp/{uuid4()}"
    expired_key, orphan_key, kept_key = [f"objects/{uuid4()}" for _ in range(3)]
    async with integration_database() as session, session.begin():
        expired = UploadIntent(
            owner_id=owner,
            temp_key=expired_key,
            expected_size=1,
            content_type="text/plain",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        session.add(expired)
        session.add(Attachment(object_key=kept_key, status="stored"))
        session.add(
            UploadIntent(
                owner_id=owner,
                temp_key=completed_temp,
                final_key=kept_key,
                expected_size=1,
                content_type="text/plain",
                status="completed",
                completed_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
    storage = ObjectStore()
    storage.keys.update((expired_key, orphan_key, kept_key, completed_temp))
    await ObjectGarbageCollector(
        SqlAlchemyObjectGarbageCollectionStorage(integration_database, cast(Any, storage))
    ).collect()
    assert expired_key in storage.deleted and orphan_key in storage.deleted
    assert kept_key not in storage.deleted
    assert completed_temp in storage.deleted
    async with integration_database() as session:
        assert (await session.get(UploadIntent, expired.id)).status == "expired"


async def test_upload_quota_is_enforced_before_s3_presign(integration_database):
    owner = f"quota-{uuid4()}"
    async with integration_database() as session:
        repository = SqlAlchemyIngestRepository(session)
        for _ in range(4):
            await repository.create_upload_intent(
                owner_id=owner,
                temporary_key=f"tmp/{uuid4()}",
                expected_size=50_000_000,
                content_type="text/plain",
                sha256="a" * 64,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        await session.commit()
        with pytest.raises(ConflictError, match="quota"):
            await repository.create_upload_intent(
                owner_id=owner,
                temporary_key=f"tmp/{uuid4()}",
                expected_size=1,
                content_type="text/plain",
                sha256="a" * 64,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
