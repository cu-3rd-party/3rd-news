from __future__ import annotations

import uuid

from lib.core.config import CLASSIFIER_EXAMPLE_DEFAULT_COUNT, CLASSIFIER_EXAMPLE_MAX_COUNT
from lib.domain import ClaimedAttempt, PipelineRuntime
from lib.infra.storage.postgres.models import (
    Attachment,
    Classifier,
    Job,
    News,
    NewsVersion,
    ProcessingAttempt,
    Setting,
)
from lib.infra.storage.postgres.repositories.classifier_example_repository import (
    ClassifierExampleRepository,
)
from lib.interactor.errors import ClassifierProtocolError, StaleAttemptError
from pydantic import HttpUrl
from sqlalchemy import select
from thirdnews_contracts import (
    CallbackSpec,
    ClassifyAttachment,
    ClassifyNews,
    ClassifyOptions,
    ClassifyRequest,
)

from .fence import PipelineFence
from .taxonomy import PipelineTaxonomy


class PipelineRequestBuilder:
    async def build(
        self, runtime: PipelineRuntime, claimed: ClaimedAttempt
    ) -> tuple[ClassifyRequest, str, str, float]:
        async with runtime.sessions() as session:
            job = await session.get(Job, claimed.job_id)
            if not PipelineFence().matches(job, claimed):
                raise StaleAttemptError()
            assert job is not None
            classifier = await session.get(Classifier, job.classifier_id)
            news = await session.get(News, job.news_id)
            attempt = await session.get(ProcessingAttempt, claimed.attempt_id)
            if classifier is None or not classifier.enabled:
                raise ClassifierProtocolError("classifier is disabled or missing")
            if news is None or attempt is None or news.current_version_id != attempt.version_id:
                raise StaleAttemptError()
            if not PipelineFence().matches_news(news, job):
                raise StaleAttemptError()
            version = await session.get(NewsVersion, attempt.version_id)
            if version is None:
                raise StaleAttemptError()
            taxonomy, axes = await PipelineTaxonomy().load(session)
            requested_axes = tuple(classifier.allowed_axes) or tuple(axes)
            requested_axes = tuple(axis for axis in requested_axes if axis in axes)
            attachments = (
                await session.scalars(
                    select(Attachment)
                    .where(Attachment.news_id == news.id, Attachment.active.is_(True))
                    .order_by(Attachment.position, Attachment.id)
                )
            ).all()
            context_row = await session.get(Setting, "classification_context")
            context_config = context_row.value or {} if context_row else {}
            context_value = context_config.get("text")
            examples = []
            if context_config.get("examples_enabled") is True:
                example_limit = min(
                    max(
                        int(
                            context_config.get("examples_limit") or CLASSIFIER_EXAMPLE_DEFAULT_COUNT
                        ),
                        1,
                    ),
                    CLASSIFIER_EXAMPLE_MAX_COUNT,
                )
                examples = await ClassifierExampleRepository(session).list_examples(
                    exclude_news_id=news.id,
                    allowed_axes=set(requested_axes),
                    limit=example_limit,
                )
            request = ClassifyRequest(
                request_id=str(uuid.uuid4()),
                job_id=str(job.id),
                attempt_id=str(attempt.id),
                news=ClassifyNews(
                    id=str(news.id),
                    version=version.number,
                    title=version.title,
                    body_md=version.body_md,
                    source_link=version.source_link,
                    source_text=version.source_text,
                    published_at=version.source_published_at,
                    received_at=news.created_at,
                    lang=version.language,
                    attachments=[
                        ClassifyAttachment(
                            kind=item.kind,
                            media_id=str(item.id),
                            mime=item.content_type,
                            filename=item.filename,
                            caption=item.caption,
                            extracted_text=item.extracted_text,
                        )
                        for item in attachments
                    ],
                    extra=version.extra,
                ),
                taxonomy=taxonomy,
                options=ClassifyOptions(
                    allowed_axes=list(requested_axes),
                    min_confidence=classifier.min_confidence,
                    config=classifier.config,
                    callback=CallbackSpec(
                        url=HttpUrl(f"{runtime.public_base_url}/api/v1/classification/callback"),
                        deadline_at=attempt.deadline_at,
                        audience=runtime.callback_audience,
                    ),
                ),
                context=str(context_value) if context_value is not None else None,
                examples=examples,
            )
            raw_request = request.model_dump_json(exclude_none=True).encode("utf-8")
            attempt.taxonomy_version = taxonomy.version
            attempt.schema_version = "2.0"
            attempt.request_payload = {
                "request_id": request.request_id,
                "job_id": request.job_id,
                "attempt_id": request.attempt_id,
                "news_id": request.news.id,
                "news_version": request.news.version,
                "allowed_axes": list(requested_axes),
            }
            if runtime.protector is not None:
                attempt.raw_request_encrypted = runtime.protector.encrypt(raw_request)
            await session.commit()
            return (
                request,
                classifier.endpoint,
                str(classifier.config.get("node_id") or classifier.slug),
                min(float(classifier.timeout_seconds), runtime.request_timeout),
            )
