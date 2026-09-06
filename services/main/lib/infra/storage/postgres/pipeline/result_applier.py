from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lib.dto.claimed_attempt import ClaimedAttempt
from lib.dto.pipeline_runtime import PipelineRuntime
from lib.infra.storage.postgres.models import Classifier, Job, News, ProcessingAttempt
from lib.interactor.errors import ClassifierProtocolError, StaleAttemptError
from lib.interactor.use_cases.processing.classification_response_policy import (
    ClassificationResponsePolicy,
)
from lib.interactor.use_cases.processing.normalization import normalize_labels
from thirdnews_contracts import CallbackResult

from .fence import PipelineFence
from .opinion_writer import PipelineOpinionWriter
from .taxonomy import PipelineTaxonomy


class PipelineResultApplier:
    async def apply(
        self,
        runtime: PipelineRuntime,
        claimed: ClaimedAttempt,
        response: CallbackResult | Any,
        raw_body: bytes,
        *,
        callback_token_hash: str | None = None,
    ) -> None:
        if ClassificationResponsePolicy().failure(response) is not None:
            raise ClassifierProtocolError("failed classifier response cannot be applied")
        now = datetime.now(UTC)
        async with runtime.sessions() as session, session.begin():
            job = await session.get(Job, claimed.job_id, with_for_update=True)
            attempt = await session.get(ProcessingAttempt, claimed.attempt_id, with_for_update=True)
            if job is None or not PipelineFence().matches(job, claimed) or attempt is None:
                raise StaleAttemptError()
            if attempt.status not in {"running", "waiting_callback"}:
                raise StaleAttemptError()
            if callback_token_hash is not None:
                if attempt.callback_token_hash is not None:
                    if (
                        attempt.callback_token_hash == callback_token_hash
                        and attempt.status == "succeeded"
                    ):
                        return
                    raise ClassifierProtocolError("callback token was already used")
                if now > attempt.deadline_at:
                    raise StaleAttemptError("callback deadline has passed")
                attempt.callback_token_hash = callback_token_hash
                attempt.callback_received_at = now
            news = await session.get(News, job.news_id, with_for_update=True)
            classifier = await session.get(Classifier, job.classifier_id)
            if (
                news is None
                or classifier is None
                or news.current_version_id != attempt.version_id
                or not PipelineFence().matches_news(news, job)
            ):
                raise StaleAttemptError()
            expected_node_id = str(classifier.config.get("node_id") or classifier.slug)
            if response.classifier != classifier.slug or response.node_id != expected_node_id:
                raise ClassifierProtocolError("classifier identity does not match registration")
            taxonomy, axes = await PipelineTaxonomy().load(session)
            allowed = set(classifier.allowed_axes) or set(axes)
            normalized = normalize_labels(
                response.labels,
                axes=axes,
                allowed_axes=allowed,
                min_confidence=classifier.min_confidence,
            )
            attempt.status = "succeeded"
            attempt.completed_at = now
            opinions = PipelineOpinionWriter()
            await opinions.append(session, news, attempt, classifier, normalized, axes)
            await session.flush()
            await opinions.materialize(session, news)
            if runtime.protector is not None:
                attempt.raw_payload_encrypted = runtime.protector.encrypt(raw_body)
            result = response.model_dump(mode="json", exclude_none=True)
            if isinstance(result.get("trace"), dict):
                result["trace"].pop("request_payload", None)
                result["trace"].pop("raw_response", None)
            attempt.validated_result = {
                **result,
                "labels": [opinions.label_json(label) for label in normalized],
            }
            attempt.evidence = {
                f"{label.axis}:{label.value}": list(label.evidence) for label in normalized
            }
            trace = getattr(response, "trace", None)
            if trace is not None:
                attempt.model = {
                    "provider": trace.provider,
                    "model": trace.model,
                    "parameters": trace.parameters,
                }
                attempt.prompt_version = trace.prompt_version
                attempt.schema_version = trace.schema_version
                attempt.taxonomy_version = trace.taxonomy_version
                attempt.duration_ms = trace.duration_ms
                if trace.error:
                    attempt.error_detail = "classifier_reported_error"
            job.status = "succeeded"
            job.result = {
                "attempt_id": str(attempt.id),
                "labels": [opinions.label_json(label) for label in normalized],
            }
            job.completed_at = now
            job.owner = None
            job.lease_until = None
            job.last_error = None
