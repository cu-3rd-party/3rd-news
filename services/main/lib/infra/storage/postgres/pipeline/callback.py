from __future__ import annotations

import hashlib
import uuid

from lib.domain import ClaimedAttempt, PipelineRuntime
from lib.infra.storage.postgres.models import Classifier, Job, ProcessingAttempt
from lib.interactor.errors import ClassifierProtocolError, StaleAttemptError
from lib.interactor.use_cases.processing.classification_response_policy import (
    ClassificationResponsePolicy,
)
from thirdnews_contracts import CallbackResult, SignatureError, bearer_token, verify_message

from .finalizer import PipelineFinalizer
from .result_applier import PipelineResultApplier


class PipelineCallback:
    async def apply(
        self, runtime: PipelineRuntime, raw_body: bytes, authorization: str | None
    ) -> str:
        try:
            response = CallbackResult.model_validate_json(raw_body)
            job_id = uuid.UUID(response.job_id)
            attempt_id = uuid.UUID(response.attempt_id)
        except (ValueError, TypeError) as error:
            raise ClassifierProtocolError("invalid callback body") from error
        async with runtime.sessions() as session:
            attempt = await session.get(ProcessingAttempt, attempt_id)
            job = await session.get(Job, job_id)
            classifier = await session.get(Classifier, attempt.classifier_id) if attempt else None
            if attempt is None or job is None or classifier is None:
                raise StaleAttemptError("callback attempt does not exist")
            if not classifier.signing_public_key:
                raise ClassifierProtocolError("classifier has no callback verification key")
            expected_issuer = str(
                classifier.config.get("issuer")
                or classifier.config.get("node_id")
                or classifier.slug
            )
            try:
                claims = verify_message(
                    classifier.signing_public_key,
                    bearer_token(authorization),
                    raw_body,
                    issuer=expected_issuer,
                    audience=runtime.callback_audience,
                    job_id=str(job.id),
                    attempt_id=str(attempt.id),
                    node_id=response.node_id,
                )
            except SignatureError as error:
                raise PermissionError("invalid callback signature") from error
            token_hash = hashlib.sha256(claims.token_id.encode()).hexdigest()
            if attempt.callback_token_hash is not None:
                if attempt.callback_token_hash == token_hash and attempt.status == "succeeded":
                    return "duplicate"
                raise ClassifierProtocolError("callback token was already used")
            claimed = ClaimedAttempt(job.id, attempt.id, attempt.generation)
        failure = ClassificationResponsePolicy().failure(response)
        if failure is not None:
            error, retryable = failure
            await PipelineFinalizer().fail(
                runtime,
                claimed,
                error,
                callback_token_hash=token_hash,
                raw_body=raw_body,
                retryable=retryable,
            )
        else:
            await PipelineResultApplier().apply(
                runtime,
                claimed,
                response,
                raw_body,
                callback_token_hash=token_hash,
            )
        return "applied"
