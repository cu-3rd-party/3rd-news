from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from lib.core.service_factory import service_factory
from lib.dto.requests import (
    UploadCompleteRequest,
    UploadPresignRequest,
)
from lib.interactor.errors import ConflictError, NotFoundError, ValidationError
from lib.interactor.use_cases.upload_administration import UploadAdministration

from .common import error_status
from .dependencies import DbSession, IngestPrincipal

router = APIRouter()


@router.post("/api/v1/uploads/presign", status_code=201)
async def presign_upload(
    payload: UploadPresignRequest, request: Request, session: DbSession, principal: IngestPrincipal
) -> dict:
    settings = request.app.state.settings
    service = UploadAdministration(
        service_factory.ingest(session),
        request.app.state.storage,
        max_bytes=settings.upload_max_bytes,
        presign_ttl_seconds=settings.file_presign_ttl_seconds,
    )
    try:
        return await service.presign(
            owner_id=principal.subject,
            size=payload.size,
            content_type=payload.content_type,
            sha256=payload.sha256,
        )
    except ValidationError as error:
        if str(error) == "file is too large":
            raise HTTPException(413, str(error)) from error
        raise error_status(error) from error


@router.post("/api/v1/uploads/complete")
async def complete_upload(
    payload: UploadCompleteRequest, request: Request, session: DbSession, principal: IngestPrincipal
) -> dict:
    settings = request.app.state.settings
    service = UploadAdministration(
        service_factory.ingest(session),
        request.app.state.storage,
        max_bytes=settings.upload_max_bytes,
        presign_ttl_seconds=settings.file_presign_ttl_seconds,
    )
    try:
        return await service.complete(payload.upload_id, principal.subject)
    except NotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except ConflictError as error:
        status = 410 if str(error) == "upload expired" else 409
        raise HTTPException(status, str(error)) from error
