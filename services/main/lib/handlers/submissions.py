from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, Request
from pydantic import ValidationError as PydanticValidationError
from thirdnews_contracts import (
    IngestResult,
    IngestStatus,
    NewsSubmission,
)

from lib.core.service_factory import service_factory
from lib.interactor.errors import ConflictError, ValidationError
from lib.interactor.use_cases.submission_acceptance import SubmissionAcceptance

from .common import error_status
from .dependencies import DbSession, IngestPrincipal

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


@router.post("/api/v1/news", status_code=202, response_model=IngestResult)
async def submit_news(
    request: Request,
    principal: IngestPrincipal,
    payload: Annotated[NewsSubmission | dict[str, Any], Body()],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestResult:
    values = (
        payload.model_dump(mode="json") if isinstance(payload, NewsSubmission) else dict(payload)
    )
    payload_key = values.get("idempotency_key")
    if payload_key and idempotency_key and payload_key != idempotency_key:
        raise HTTPException(409, "payload and header idempotency keys differ")
    if idempotency_key and not payload_key:
        values["idempotency_key"] = idempotency_key
    try:
        submission = NewsSubmission.model_validate(values)
    except PydanticValidationError as error:
        fields = [".".join(str(part) for part in issue["loc"]) for issue in error.errors()]
        raise HTTPException(422, f"invalid fields: {', '.join(fields[:10])}") from error
    try:
        accepted = await ingest_service(request).execute(
            submission,
            principal_id=principal.subject,
            bound_source_id=principal.source_id,
        )
    except (ConflictError, ValidationError) as error:
        raise error_status(error) from error
    return IngestResult(
        submission_id=str(accepted.submission_id),
        status=IngestStatus(accepted.status),
        received_at=accepted.received_at,
    )


@router.get("/api/v1/submissions/{submission_id}")
async def submission_status(
    submission_id: uuid.UUID, session: DbSession, principal: IngestPrincipal
) -> dict:
    item = await service_factory.ingest(session).submission(submission_id)
    if item is None:
        raise HTTPException(404, "submission not found")
    if (
        principal.source_id
        and item.source_id != principal.source_id
        and not principal.allows("admin")
    ):
        raise HTTPException(404, "submission not found")
    return {
        "id": str(item.id),
        "status": item.status,
        "news_id": str(item.news_id) if item.news_id else None,
        "received_at": item.received_at,
    }
