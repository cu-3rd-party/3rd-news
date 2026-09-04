"""Work the background worker performs: asking classifiers, fetching media."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from thirdnews_contracts import (
    ClassifyAttachment,
    ClassifyNews,
    ClassifyOptions,
    ClassifyRequest,
    ClassifyResponse,
    ProposedLabel,
    sign_payload,
)

from . import knowledge
from .config import settings
from .labels import (
    entries_from,
    mark_classification_finished,
    record_labels,
    resolve_taxonomy_ids,
)
from .models import Attachment, ClassificationJob, Classifier, News
from .storage import guess_kind, save_bytes
from .taxonomy import build_taxonomy

logger = logging.getLogger("3rdnews.dispatcher")


class RetryJob(Exception):
    """Raised to tell the worker loop to put this job back on the queue."""


#: Statuses that still owe us an answer.
OPEN_JOB_STATUSES = ("queued", "running", "awaiting_callback")


async def _build_request(
    session: AsyncSession, news: News, classifier: Classifier, request_id: str
) -> ClassifyRequest:
    taxonomy = await build_taxonomy(session, classifier.facets or None)
    # Контекст организации и примеры ручной разметки — то, чего в самой
    # новости нет: расшифровки сокращений и принятые у редакции решения.
    context = await knowledge.get_context(session)
    examples = await knowledge.collect_examples(session, exclude_news_id=news.id)
    return ClassifyRequest(
        request_id=request_id,
        news=ClassifyNews(
            id=str(news.id),
            title=news.title,
            body_md=news.body_md,
            source_link=news.source_link,
            source_text=news.source_text,
            published_at=news.published_at,
            received_at=news.received_at,
            lang=news.lang,
            attachments=[
                ClassifyAttachment(
                    kind=item.kind,
                    url=item.original_url,
                    mime=item.mime,
                    filename=item.filename,
                    caption=item.caption,
                )
                for item in news.attachments
            ],
            extra=news.extra or {},
        ),
        taxonomy=taxonomy,
        context=context,
        examples=examples,
        options=ClassifyOptions(
            facets=list(classifier.facets or []),
            min_confidence=classifier.min_confidence,
            config=classifier.config or {},
            callback_url=(
                f"{settings.public_base_url.rstrip('/')}/api/v1/classification/callback"
            ),
        ),
    )


async def run_classification_job(session: AsyncSession, job_id: str) -> None:
    """Ask one classifier about one news item and store what it says."""

    job = (
        await session.execute(
            select(ClassificationJob)
            .options(
                selectinload(ClassificationJob.classifier),
                selectinload(ClassificationJob.news).selectinload(News.attachments),
            )
            .where(ClassificationJob.id == job_id)
        )
    ).scalar_one_or_none()
    if job is None or job.status == "done":
        return

    classifier, news = job.classifier, job.news
    if classifier is None or news is None or not classifier.is_active:
        job.status = "failed"
        job.error = "classifier is gone or disabled"
        await session.commit()
        return

    job.status = "running"
    job.attempts += 1
    await session.commit()

    payload = await _build_request(session, news, classifier, request_id=str(job.id))
    body = payload.model_dump_json().encode()
    headers = {"Content-Type": "application/json"}
    if classifier.secret:
        headers.update(sign_payload(classifier.secret, body))

    try:
        async with httpx.AsyncClient(timeout=classifier.timeout_s) as http:
            response = await http.post(
                f"{classifier.base_url}/classify", content=body, headers=headers
            )
        if response.status_code == 202:
            # The service will answer later on the callback endpoint.
            job.status = "awaiting_callback"
            classifier.last_ok_at = datetime.now(timezone.utc)
            await session.commit()
            return
        response.raise_for_status()
        result = ClassifyResponse.model_validate(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        await _fail_job(session, job, classifier, str(exc))
        return

    await apply_result(session, job, classifier, result.labels, meta=result.meta)


async def _fail_job(
    session: AsyncSession, job: ClassificationJob, classifier: Classifier, error: str
) -> None:
    logger.warning("classifier %s failed on job %s: %s", classifier.slug, job.id, error)
    classifier.last_error = error[:2000]
    classifier.last_error_at = datetime.now(timezone.utc)
    if job.attempts >= settings.classification_max_attempts:
        job.status = "failed"
        job.error = error[:2000]
        job.finished_at = datetime.now(timezone.utc)
        await session.commit()
        await finish_if_settled(session, job.news_id)
    else:
        job.status = "queued"
        job.error = error[:2000]
        await session.commit()
        raise RetryJob(str(job.id))


async def apply_result(
    session: AsyncSession,
    job: ClassificationJob,
    classifier: Classifier,
    labels: list[ProposedLabel],
    meta: dict | None = None,
) -> None:
    """Record a classifier's proposals and, if it was the last one, settle."""

    grouped: dict[str, list[str]] = {}
    confidences: dict[tuple[str, str], float] = {}
    reasons: dict[tuple[str, str], str] = {}
    for label in labels:
        grouped.setdefault(label.facet, []).append(label.value)
        confidences[(label.facet, label.value)] = label.confidence
        if label.reason:
            reasons[(label.facet, label.value)] = label.reason

    resolved = await resolve_taxonomy_ids(session, grouped)
    await record_labels(
        session,
        job.news_id,
        entries_from(resolved, confidences, reasons),
        origin="classifier",
        origin_key=classifier.slug,
    )

    job.status = "done"
    job.error = None
    job.result = {
        "labels": [label.model_dump(mode="json") for label in labels],
        "meta": meta or {},
    }
    job.finished_at = datetime.now(timezone.utc)
    classifier.last_ok_at = job.finished_at
    classifier.last_error = None
    await session.commit()

    await finish_if_settled(session, job.news_id)


async def finish_if_settled(session: AsyncSession, news_id: uuid.UUID) -> None:
    """Mark the item classified once no job is still owed an answer."""

    open_jobs = (
        await session.execute(
            select(ClassificationJob.id).where(
                ClassificationJob.news_id == news_id,
                ClassificationJob.status.in_(OPEN_JOB_STATUSES),
            )
        )
    ).first()
    if open_jobs is not None:
        return
    await mark_classification_finished(session, news_id)
    await session.commit()


async def fetch_attachment(session: AsyncSession, attachment_id: str) -> None:
    """Download an attachment a parser referenced by URL."""

    attachment = (
        await session.execute(select(Attachment).where(Attachment.id == attachment_id))
    ).scalar_one_or_none()
    if attachment is None or attachment.storage_path or not attachment.original_url:
        return

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
            async with http.stream("GET", attachment.original_url) as response:
                response.raise_for_status()
                declared = int(response.headers.get("content-length") or 0)
                if declared > settings.max_attachment_bytes:
                    raise ValueError(f"attachment too large: {declared} bytes")

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > settings.max_attachment_bytes:
                        # Servers lie about content-length; stop on the real size.
                        raise ValueError("attachment exceeded the size limit while downloading")
                    chunks.append(chunk)
                mime = response.headers.get("content-type", "").split(";")[0].strip()

        stored = save_bytes(b"".join(chunks), attachment.filename, attachment.mime or mime)
    except (httpx.HTTPError, ValueError, OSError) as exc:
        attachment.status = "failed"
        attachment.error = str(exc)[:2000]
        await session.commit()
        return

    for field, value in stored.items():
        setattr(attachment, field, value)
    if attachment.kind == "file":
        attachment.kind = guess_kind(attachment.mime, attachment.filename)
    attachment.status = "stored"
    attachment.error = None
    await session.commit()
