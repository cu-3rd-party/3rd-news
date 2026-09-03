"""Turning a `NewsSubmission` into stored rows and queued work."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from thirdnews_contracts import IngestResult, IngestStatus, NewsSubmission

from . import queue, storage
from .config import settings
from .labels import (
    entries_from,
    recompute_effective,
    record_labels,
    resolve_taxonomy_ids,
)
from .models import ApiKey, Attachment, ClassificationJob, Classifier, News, Source

logger = logging.getLogger("3rdnews.ingest")

_WHITESPACE = re.compile(r"\s+")
#: Same body from the same source inside this window is treated as a repost.
DEDUP_WINDOW = timedelta(days=30)


def content_hash(title: str | None, body_md: str) -> str:
    normalised = _WHITESPACE.sub(" ", f"{title or ''}\n{body_md}").strip().lower()
    return hashlib.sha256(normalised.encode()).hexdigest()


async def resolve_source(
    session: AsyncSession, source_key: str | None, api_key: ApiKey | None
) -> Source | None:
    """Find the source, creating an inactive stub for keys we have not seen.

    Auto-creating means a brand-new third-party parser works the moment it has
    a key, and the admin only has to fill in the title afterwards.
    """

    if not source_key and api_key is not None and api_key.source_id:
        return (
            await session.execute(select(Source).where(Source.id == api_key.source_id))
        ).scalar_one_or_none()
    if not source_key:
        return None

    slug = slugify(source_key)[:120]
    source = (
        await session.execute(select(Source).where(Source.slug == slug))
    ).scalar_one_or_none()
    if source is None:
        source = Source(slug=slug, title=source_key, kind="other")
        session.add(source)
        await session.flush()
    return source


async def _find_duplicate(
    session: AsyncSession, source: Source | None, submission: NewsSubmission, digest: str
) -> News | None:
    if source is not None and submission.external_id:
        existing = (
            await session.execute(
                select(News).where(
                    News.source_id == source.id, News.external_id == submission.external_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    since = datetime.now(timezone.utc) - DEDUP_WINDOW
    query = select(News).where(News.dedup_hash == digest, News.received_at >= since)
    if source is not None:
        query = query.where(News.source_id == source.id)
    return (await session.execute(query.limit(1))).scalar_one_or_none()


async def create_news(
    session: AsyncSession,
    submission: NewsSubmission,
    *,
    api_key: ApiKey | None = None,
    uploads: dict[str, tuple[str | None, bytes, str | None]] | None = None,
) -> IngestResult:
    """Store one submission. Idempotent per `(source, external_id)`."""

    source = await resolve_source(session, submission.source_key, api_key)
    digest = content_hash(submission.title, submission.body_md)

    duplicate = await _find_duplicate(session, source, submission, digest)
    if duplicate is not None:
        return IngestResult(
            id=str(duplicate.id),
            status=IngestStatus.DUPLICATE,
            received_at=duplicate.received_at,
        )

    news = News(
        source_id=source.id if source else None,
        external_id=submission.external_id,
        title=submission.title,
        body_md=submission.body_md,
        source_link=str(submission.source_link) if submission.source_link else None,
        source_text=submission.source_text or (source.title if source else None),
        lang=submission.lang,
        published_at=submission.published_at,
        received_at=datetime.now(timezone.utc),
        dedup_hash=digest,
        extra=submission.extra or {},
        ingested_by_key_id=api_key.id if api_key else None,
    )
    session.add(news)
    await session.flush()

    await _attach(session, news, submission, uploads or {})
    await _apply_initial_labels(session, news, submission, source)

    if source is not None:
        source.last_ingest_at = news.received_at

    jobs: list[ClassificationJob] = []
    if source is not None and source.skip_classification:
        news.classified_at = news.received_at
    else:
        jobs = await schedule_classification(session, news)

    await recompute_effective(session, news.id)
    pending_media = [a.id for a in news.attachments if a.storage_path is None]
    job_ids = [job.id for job in jobs]
    await session.commit()

    # Queued only after the transaction lands, so a worker can never pick up a
    # job whose row is not visible yet.
    for attachment_id in pending_media:
        await queue.enqueue(queue.QUEUE_MEDIA, {"attachment_id": str(attachment_id)})
    for job_id in job_ids:
        await queue.enqueue(queue.QUEUE_CLASSIFY, {"job_id": str(job_id)})

    return IngestResult(
        id=str(news.id), status=IngestStatus.CREATED, received_at=news.received_at
    )


async def _attach(
    session: AsyncSession,
    news: News,
    submission: NewsSubmission,
    uploads: dict[str, tuple[str | None, bytes, str | None]],
) -> None:
    for position, item in enumerate(submission.attachments):
        if item.upload_name:
            upload = uploads.get(item.upload_name)
            if upload is None:
                continue
            filename, data, mime = upload
            if len(data) > settings.max_attachment_bytes:
                logger.warning("attachment %s exceeds the size limit, skipping", filename)
                continue
            try:
                stored = storage.save_bytes(data, item.filename or filename, item.mime or mime)
            except (ValueError, OSError) as exc:
                # One unusable file must not cost us the news item itself.
                logger.warning("could not store attachment %s: %s", filename, exc)
                continue
            session.add(
                Attachment(
                    news_id=news.id,
                    kind=item.kind.value
                    if item.kind.value != "file"
                    else storage.guess_kind(stored["mime"], stored["filename"]),
                    caption=item.caption,
                    position=item.position or position,
                    status="stored",
                    **stored,
                )
            )
        else:
            session.add(
                Attachment(
                    news_id=news.id,
                    kind=item.kind.value,
                    original_url=str(item.url),
                    filename=item.filename,
                    mime=item.mime,
                    caption=item.caption,
                    position=item.position or position,
                    status="pending",
                )
            )
    await session.flush()
    await session.refresh(news, ["attachments"])


async def _apply_initial_labels(
    session: AsyncSession, news: News, submission: NewsSubmission, source: Source | None
) -> None:
    if source is not None and source.default_labels:
        resolved = await resolve_taxonomy_ids(session, source.default_labels)
        await record_labels(
            session,
            news.id,
            entries_from(resolved),
            origin="source_default",
            origin_key=source.slug,
        )
    if submission.labels:
        resolved = await resolve_taxonomy_ids(session, submission.labels)
        await record_labels(
            session,
            news.id,
            entries_from(resolved),
            origin="parser",
            origin_key=source.slug if source else "",
        )


async def schedule_classification(
    session: AsyncSession, news: News, *, only_classifier_id: uuid.UUID | None = None
) -> list[ClassificationJob]:
    """Create (or reset) one job per active classifier.

    Returns the jobs; publish them with `enqueue_jobs` once the transaction has
    been committed.
    """

    query = select(Classifier).where(Classifier.is_active.is_(True))
    if only_classifier_id is not None:
        query = select(Classifier).where(Classifier.id == only_classifier_id)
    classifiers = (await session.execute(query)).scalars().all()

    jobs: list[ClassificationJob] = []
    for classifier in classifiers:
        job = (
            await session.execute(
                select(ClassificationJob).where(
                    ClassificationJob.news_id == news.id,
                    ClassificationJob.classifier_id == classifier.id,
                )
            )
        ).scalar_one_or_none()
        if job is None:
            job = ClassificationJob(news_id=news.id, classifier_id=classifier.id)
            session.add(job)
        job.status = "queued"
        job.attempts = 0
        job.error = None
        job.finished_at = None
        jobs.append(job)

    await session.flush()
    if not jobs:
        # Nothing to ask: the item is as classified as it will ever be.
        news.classified_at = datetime.now(timezone.utc)
        await session.flush()
    return jobs


async def enqueue_jobs(jobs: list[ClassificationJob]) -> None:
    """Publish jobs to the worker queue. Call after the transaction commits."""

    for job in jobs:
        await queue.enqueue(queue.QUEUE_CLASSIFY, {"job_id": str(job.id)})
