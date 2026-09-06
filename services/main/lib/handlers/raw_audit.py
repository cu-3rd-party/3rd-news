from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from lib.core.service_factory import service_factory
from lib.infra.clients.auth import Principal
from lib.interactor.use_cases.processing.raw_payloads import RawPayloadProtector

from .common import actor
from .dependencies import DbSession, require

router = APIRouter(prefix="/api/v1/admin/attempts", tags=["audit"])
RawPrincipal = Annotated[Principal, Depends(require("raw_audit"))]


@router.get("/{attempt_id}/raw")
async def read_raw(
    attempt_id: UUID,
    request: Request,
    response: Response,
    session: DbSession,
    principal: RawPrincipal,
) -> dict:
    settings = request.app.state.settings
    if not settings.raw_audit_encryption_key:
        raise HTTPException(503, "raw audit is not configured")
    encrypted = await service_factory.raw_audit(session).read(
        attempt_id, actor=actor(principal), retention_days=settings.raw_audit_retention_days
    )
    protector = RawPayloadProtector(settings.raw_audit_encryption_key)
    response.headers["Cache-Control"] = "no-store"
    return {
        name: protector.decrypt(value).decode("utf-8", errors="replace") if value else None
        for name, value in zip(("request", "response"), encrypted, strict=True)
    }
