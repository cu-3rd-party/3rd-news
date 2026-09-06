from __future__ import annotations

import uuid

from fastapi import APIRouter

from lib.core.service_factory import service_factory
from lib.dto.requests import (
    EditorialRuleInput,
)
from lib.infra.storage.postgres.repositories.editorial_rule_repository import (
    EditorialRuleRepository,
)
from lib.interactor.errors import ConflictError, NotFoundError, ValidationError

from .common import actor, error_status
from .dependencies import AdminPrincipal, DbSession

router = APIRouter()


def editorial_rule_storage(session: DbSession) -> EditorialRuleRepository:
    return service_factory.editorial_rule(session)


@router.get("/api/v1/admin/editorial-rules")
async def editorial_rules(session: DbSession, principal: AdminPrincipal) -> dict:
    del principal
    return {"items": await editorial_rule_storage(session).list_editorial_rules()}


@router.post("/api/v1/admin/editorial-rules", status_code=201)
async def create_editorial_rule(
    payload: EditorialRuleInput,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    try:
        return await editorial_rule_storage(session).create_editorial_rule(
            payload.model_dump(mode="json"), actor(principal)
        )
    except ConflictError as error:
        raise error_status(error) from error


@router.patch("/api/v1/admin/editorial-rules/{rule_id}", status_code=201)
async def revise_editorial_rule(
    rule_id: uuid.UUID,
    payload: EditorialRuleInput,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    try:
        return await editorial_rule_storage(session).revise_editorial_rule(
            rule_id, payload.model_dump(mode="json"), actor(principal)
        )
    except (ConflictError, NotFoundError, ValidationError) as error:
        raise error_status(error) from error


@router.delete("/api/v1/admin/editorial-rules/{rule_id}", status_code=204)
async def disable_editorial_rule(
    rule_id: uuid.UUID,
    session: DbSession,
    principal: AdminPrincipal,
) -> None:
    try:
        await editorial_rule_storage(session).disable_editorial_rule(rule_id, actor(principal))
    except (ConflictError, NotFoundError) as error:
        raise error_status(error) from error
