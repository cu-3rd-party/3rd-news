from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from lib.core.service_factory import service_factory
from lib.dto.requests import (
    ApiKeyInput,
)
from lib.interactor.errors import ConflictError, NotFoundError
from lib.interactor.interfaces.storage.api_key import ApiKeyStorage

from .common import actor, error_status
from .dependencies import AdminPrincipal, DbSession

router = APIRouter()


def api_key_storage(session: DbSession) -> ApiKeyStorage:
    return service_factory.api_key(session)


@router.get("/api/v1/admin/api-keys")
async def api_keys(session: DbSession, principal: AdminPrincipal) -> dict:
    del principal
    return {"items": await api_key_storage(session).list_api_keys()}


@router.post("/api/v1/admin/api-keys", status_code=201)
async def create_api_key(
    payload: ApiKeyInput,
    request: Request,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    allowed = {"read", "ingest", "editor", "admin", "raw_audit"}
    if not set(payload.scopes) <= allowed:
        raise HTTPException(422, "unknown API key scope")
    secret, prefix, digest = request.app.state.auth.generate_api_key()
    values = {
        **payload.model_dump(mode="json"),
        "prefix": prefix,
        "key_hash": digest,
    }
    try:
        item = await api_key_storage(session).create_api_key(values, actor(principal))
    except ConflictError as error:
        raise error_status(error) from error
    return {"key": item, "secret": secret}


@router.post("/api/v1/admin/api-keys/{key_id}/revoke")
async def revoke_api_key(key_id: uuid.UUID, session: DbSession, principal: AdminPrincipal) -> dict:
    try:
        return await api_key_storage(session).revoke_api_key(key_id, actor(principal))
    except NotFoundError as error:
        raise error_status(error) from error
