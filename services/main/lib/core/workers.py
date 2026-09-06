from __future__ import annotations

import asyncio
import signal
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from lib.core.config import Settings
from lib.infra.clients.classifier import ClassifierClient
from lib.infra.clients.http import SafeFetcher, UrlPolicy
from lib.infra.clients.nats import (
    DatabaseInboxHandler,
    DurableConsumer,
    JetStreamBroker,
    OutboxPublisher,
    StreamSettings,
)
from lib.infra.clients.search import MeiliSearchClient, SearchIndexer
from lib.infra.storage.postgres.attachment_processing_storage import (
    SqlAlchemyAttachmentProcessingStorage,
)
from lib.infra.storage.postgres.database import Database
from lib.infra.storage.postgres.models import Job, News, SearchProjection
from lib.infra.storage.postgres.object_gc_storage import (
    SqlAlchemyObjectGarbageCollectionStorage,
)
from lib.infra.storage.postgres.pipeline import SqlAlchemyPipelineStorage
from lib.infra.storage.postgres.pipeline_coordinator_storage import (
    SqlAlchemyPipelineCoordinatorStorage,
)
from lib.infra.storage.postgres.rematerialization_storage import (
    SqlAlchemyRematerializationStorage,
)
from lib.infra.storage.s3 import S3ObjectStore
from lib.interactor.use_cases.processing import (
    AttachmentWorker,
    PipelineCoordinator,
    RawPayloadProtector,
)
from lib.interactor.use_cases.processing.object_gc import ObjectGarbageCollector
from lib.interactor.use_cases.processing.pipeline_worker import PipelineWorker
from lib.interactor.use_cases.rematerialization import RematerializationWorker


async def run_worker(mode: str, settings: Settings) -> None:

    if mode not in {"worker-outbox", "worker-pipeline", "worker-index"}:
        raise ValueError(f"unknown worker mode: {mode}")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    database = Database(settings.db_url)
    try:
        await database.ready()
        if mode == "worker-outbox":
            await _run_outbox(database, settings, stop)
        elif mode == "worker-pipeline":
            await _run_pipeline(database, settings, stop)
        else:
            await _run_index(database, settings, stop)
    finally:
        await database.close()


def _broker(settings: Settings, name: str) -> JetStreamBroker:
    return JetStreamBroker(
        settings.broker_url,
        settings=StreamSettings(
            name=settings.broker_stream,
            subjects=(f"{settings.broker_subject_prefix}.>",),
        ),
        client_name=f"thirdnews-{name}-{settings.worker_node_id}",
        connect_timeout=settings.broker_connect_timeout,
    )


def _storage(settings: Settings) -> S3ObjectStore:
    return S3ObjectStore(
        endpoint_url=settings.file_endpoint,
        public_endpoint_url=settings.file_public_endpoint,
        bucket=settings.file_bucket,
        access_key=settings.file_access_key_value,
        secret_key=settings.file_secret_key_value,
        region=settings.file_region,
        presign_ttl_seconds=settings.file_presign_ttl_seconds,
        max_upload_bytes=settings.upload_max_bytes,
    )


def _fetcher(settings: Settings) -> SafeFetcher:
    return SafeFetcher(
        policy=UrlPolicy.with_service_hosts(
            settings.ssrf_allow_hosts,
            max_redirects=settings.fetch_max_redirects,
        ),
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
    )


async def _run_outbox(database: Database, settings: Settings, stop: asyncio.Event) -> None:
    async with _broker(settings, "outbox") as broker:
        publisher = OutboxPublisher(
            database.session_factory,
            broker,
            owner=settings.worker_node_id,
            subject_prefix=settings.broker_subject_prefix,
            batch_size=settings.worker_batch_size,
            lease_seconds=settings.worker_lease_seconds,
            poll_seconds=settings.worker_poll_seconds,
        )
        await publisher.run(stop=stop)


async def _run_pipeline(database: Database, settings: Settings, stop: asyncio.Event) -> None:
    attachment_fetcher = _fetcher(settings)
    classifier_fetcher = SafeFetcher(
        policy=UrlPolicy.with_service_hosts(
            settings.classifier_service_hosts,
            max_redirects=settings.fetch_max_redirects,
        ),
        timeout_seconds=settings.classifier_request_timeout_seconds,
        max_bytes=settings.classifier_response_max_bytes,
    )
    storage = _storage(settings)
    protector = (
        RawPayloadProtector(settings.raw_audit_encryption_key)
        if settings.raw_audit_encryption_key
        else None
    )
    classifier = ClassifierClient(
        private_key=settings.auth_private_key,
        issuer=settings.classifier_issuer,
        audience=settings.classifier_audience,
        node_id=settings.worker_node_id,
        url_validator=classifier_fetcher,
        timeout_seconds=settings.classifier_request_timeout_seconds,
        response_max_bytes=settings.classifier_response_max_bytes,
    )
    pipeline = PipelineWorker(
        database.session_factory,
        classifier,
        storage=SqlAlchemyPipelineStorage(),
        node_id=settings.worker_node_id,
        public_base_url=settings.public_base_url,
        callback_audience=settings.callback_audience,
        callback_timeout_seconds=settings.callback_timeout_seconds,
        request_timeout_seconds=settings.classifier_request_timeout_seconds,
        lease_seconds=settings.worker_lease_seconds,
        poll_seconds=settings.worker_poll_seconds,
        cooldown_seconds=settings.pipeline_cooldown_seconds,
        raw_retention_days=settings.raw_audit_retention_days,
        raw_payload_protector=protector,
    )
    attachments = AttachmentWorker(
        SqlAlchemyAttachmentProcessingStorage(
            database.session_factory,
            attachment_fetcher,
            storage,
            node_id=settings.worker_node_id,
            lease_seconds=settings.worker_lease_seconds,
            poll_seconds=settings.worker_poll_seconds,
            cooldown_seconds=settings.pipeline_cooldown_seconds,
        )
    )
    coordinator = PipelineCoordinator(
        SqlAlchemyPipelineCoordinatorStorage(
            database.session_factory,
            node_id=settings.worker_node_id,
            max_attempts=settings.max_attempts,
            cooldown_seconds=settings.pipeline_cooldown_seconds,
            lease_seconds=settings.worker_lease_seconds,
            poll_seconds=settings.worker_poll_seconds,
        ),
        poll_seconds=settings.worker_poll_seconds,
    )
    rematerialization = RematerializationWorker(
        SqlAlchemyRematerializationStorage(
            database.session_factory,
            node_id=settings.worker_node_id,
            lease_seconds=settings.worker_lease_seconds,
            cooldown_seconds=settings.pipeline_cooldown_seconds,
        ),
        poll_seconds=settings.worker_poll_seconds,
    )
    async with _broker(settings, "pipeline") as broker:
        inbox = DatabaseInboxHandler(
            database.session_factory,
            consumer_name="pipeline-v2",
            callback=_release_referenced_job,
        )
        consumer = DurableConsumer(
            broker,
            stream=settings.broker_stream,
            subject=f"{settings.broker_subject_prefix}.>",
            durable="pipeline-v2",
            max_deliver=settings.max_attempts,
            ack_wait_seconds=settings.worker_lease_seconds,
            batch_size=settings.worker_batch_size,
        )
        async with asyncio.TaskGroup() as group:
            group.create_task(consumer.run(inbox, stop=stop))
            group.create_task(coordinator.run(stop=stop))
            group.create_task(
                ObjectGarbageCollector(
                    SqlAlchemyObjectGarbageCollectionStorage(database.session_factory, storage)
                ).run(stop=stop)
            )
            group.create_task(pipeline.run(stop=stop, concurrency=settings.worker_concurrency))
            group.create_task(rematerialization.run(stop=stop))
            group.create_task(
                attachments.run(stop=stop, concurrency=max(1, settings.worker_concurrency // 2))
            )


async def _release_referenced_job(session: AsyncSession, payload: Mapping[str, Any]) -> None:
    nested = payload.get("payload")
    if isinstance(nested, Mapping):
        payload = nested
    raw_job_id = payload.get("job_id")
    if raw_job_id is not None:
        try:
            job_id = uuid.UUID(str(raw_job_id))
        except ValueError:
            pass
        else:
            job = await session.get(Job, job_id, with_for_update=True)
            if job is not None and job.status == "pending":
                from datetime import UTC, datetime

                job.available_at = datetime.now(UTC)
    raw_news_id = payload.get("news_id")
    if raw_news_id is None:
        return
    try:
        news_id = uuid.UUID(str(raw_news_id))
    except ValueError:
        return
    news = await session.get(News, news_id)
    if news is None:
        return
    projection = await session.get(SearchProjection, news_id, with_for_update=True)
    if projection is None:
        projection = SearchProjection(news_id=news_id)
        session.add(projection)
    requested = int(payload.get("revision") or news.revision)
    projection.desired_revision = max(projection.desired_revision or 0, requested, news.revision)
    projection.status = "pending"
    projection.task_uid = None


async def _run_index(database: Database, settings: Settings, stop: asyncio.Event) -> None:
    search = MeiliSearchClient(
        settings.search_url,
        settings.search_key_value,
        index=settings.search_index,
        timeout_seconds=settings.search_task_timeout_seconds,
    )
    try:
        await search.ready()
        indexer = SearchIndexer(
            database.session_factory,
            search,
            owner=settings.worker_node_id,
            poll_seconds=settings.worker_poll_seconds,
            lease_seconds=settings.worker_lease_seconds,
        )
        await indexer.run(stop=stop)
    finally:
        await search.close()
