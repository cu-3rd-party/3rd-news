from __future__ import annotations

from fastapi import APIRouter

from lib.core.service_factory import service_factory
from lib.dto.requests import (
    AutoPublishInput,
    ContextInput,
)
from lib.infra.storage.postgres.repositories.context_repository import ContextRepository

from .common import actor
from .dependencies import AdminPrincipal, DbSession, EditorPrincipal

router = APIRouter()


def context_storage(session: DbSession) -> ContextRepository:
    return service_factory.context(session)


@router.get("/api/v1/admin/settings/auto-publish")
async def get_auto_publish(session: DbSession, principal: AdminPrincipal) -> dict:
    del principal
    value = await context_storage(session).get_setting("auto_publish")
    return {"enabled": bool(value and value.get("enabled") is True)}


@router.put("/api/v1/admin/settings/auto-publish")
async def set_auto_publish(
    payload: AutoPublishInput,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    return await context_storage(session).set_setting(
        "auto_publish", {"enabled": payload.enabled}, actor(principal)
    )


@router.put("/api/v1/admin/classification-context")
async def set_context(payload: ContextInput, session: DbSession, principal: AdminPrincipal) -> dict:
    repository = context_storage(session)
    current = await repository.get_setting("classification_context") or {}
    values = {**current, **payload.model_dump(exclude_none=True)}
    await repository.set_setting("classification_context", values, actor(principal))
    return await repository.classification_context()


@router.get("/api/v1/admin/classification-context")
async def get_context(session: DbSession, principal: EditorPrincipal) -> dict:
    del principal
    return await context_storage(session).classification_context()
