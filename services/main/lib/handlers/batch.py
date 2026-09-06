from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import ValidationError as PydanticValidationError
from thirdnews_contracts import (
    BatchIngestResult,
    BatchItemResult,
    IngestStatus,
    NewsBatchRequest,
    NewsSubmission,
)

from lib.core.service_factory import service_factory
from lib.interactor.errors import ConflictError, ValidationError
from lib.interactor.use_cases.submission_acceptance import SubmissionAcceptance

from .dependencies import IngestPrincipal

router = APIRouter()


def ingest_service(request: Request) -> SubmissionAcceptance:
    settings = request.app.state.settings
    return SubmissionAcceptance(
        lambda: service_factory.unit_of_work(request.app.state.database.session_factory),
        cooldown_seconds=settings.pipeline_cooldown_seconds,
        max_attempts=settings.max_attempts,
        label_storage=service_factory.labels(),
        identity_storage=service_factory.submission_identity(),
        writer_storage=service_factory.submission_writer(),
    )


@router.post("/api/v1/news/batch", status_code=202, response_model=BatchIngestResult)
async def submit_news_batch(
    payload: NewsBatchRequest,
    request: Request,
    principal: IngestPrincipal,
) -> BatchIngestResult:
    results = []
    service = ingest_service(request)
    for index, item in enumerate(payload.items):
        try:
            validated = (
                item if isinstance(item, NewsSubmission) else NewsSubmission.model_validate(item)
            )
            accepted = await service.execute(
                validated,
                principal_id=principal.subject,
                bound_source_id=principal.source_id,
            )
            results.append(
                BatchItemResult(
                    index=index,
                    status=IngestStatus(accepted.status),
                    submission_id=str(accepted.submission_id),
                    received_at=accepted.received_at,
                )
            )
        except ConflictError as error:
            results.append(
                BatchItemResult(index=index, status=IngestStatus.CONFLICT, error=str(error))
            )
        except PydanticValidationError as error:
            fields = [".".join(str(part) for part in issue["loc"]) for issue in error.errors()]
            results.append(
                BatchItemResult(
                    index=index,
                    status=IngestStatus.REJECTED,
                    error=f"invalid fields: {', '.join(fields[:10])}",
                )
            )
        except ValidationError as error:
            results.append(
                BatchItemResult(index=index, status=IngestStatus.REJECTED, error=str(error))
            )
    return BatchIngestResult(results=results)
