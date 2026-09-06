from __future__ import annotations

import uuid

from fastapi import APIRouter

from lib.core.service_factory import service_factory
from lib.dto.requests import (
    SourceInput,
)
from lib.interactor.interfaces.storage.source import SourceStorage
from lib.interactor.errors import ConflictError, NotFoundError

from .common import actor, error_status
from .dependencies import AdminPrincipal, DbSession, EditorPrincipal

router = APIRouter()


def source_storage(session: DbSession) -> SourceStorage:
    return service_factory.source(session)


@router.get("/api/v1/admin/sources")
async def sources(session: DbSession, principal: EditorPrincipal) -> dict:
    del principal
    return {"items": await source_storage(session).list_sources()}


@router.post("/api/v1/admin/sources", status_code=201)
async def create_source(
    payload: SourceInput, session: DbSession, principal: AdminPrincipal
) -> dict:
    values = payload.model_dump(mode="json")
    if values.get("url") is not None:
        values["url"] = str(values["url"])
    try:
        return await source_storage(session).create_source(values, actor(principal))
    except ConflictError as error:
        raise error_status(error) from error


@router.patch("/api/v1/admin/sources/{source_id}")
async def update_source(
    source_id: uuid.UUID,
    payload: SourceInput,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    values = payload.model_dump(mode="json")
    if values.get("url") is not None:
        values["url"] = str(values["url"])
    try:
        return await source_storage(session).update_source(source_id, values, actor(principal))
    except NotFoundError as error:
        raise error_status(error) from error
