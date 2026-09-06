from __future__ import annotations

import uuid

from fastapi import APIRouter

from lib.core.service_factory import service_factory
from lib.dto.requests import FacetInput, FacetValueInput
from lib.interactor.errors import ConflictError, NotFoundError, ValidationError
from lib.interactor.use_cases.taxonomy_administration import TaxonomyAdministration

from .common import actor, error_status
from .dependencies import AdminPrincipal, DbSession, EditorPrincipal

router = APIRouter()


def service(session: DbSession) -> TaxonomyAdministration:
    return TaxonomyAdministration(service_factory.taxonomy(session))


@router.get("/api/v1/admin/facets")
async def facets(session: DbSession, principal: EditorPrincipal) -> dict:
    del principal
    return {"items": await service(session).list_facets()}


@router.post("/api/v1/admin/facets", status_code=201)
async def create_facet(payload: FacetInput, session: DbSession, principal: AdminPrincipal) -> dict:
    try:
        return await service(session).create_facet(payload.model_dump(), actor(principal))
    except ConflictError as error:
        raise error_status(error) from error


@router.patch("/api/v1/admin/facets/{facet_id}")
async def update_facet(
    facet_id: uuid.UUID,
    payload: FacetInput,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    try:
        return await service(session).update_facet(facet_id, payload.model_dump(), actor(principal))
    except (ConflictError, NotFoundError, ValidationError) as error:
        raise error_status(error) from error


@router.delete("/api/v1/admin/facets/{facet_id}", status_code=204)
async def delete_facet(facet_id: uuid.UUID, session: DbSession, principal: AdminPrincipal) -> None:
    try:
        await service(session).disable_facet(facet_id, actor(principal))
    except NotFoundError as error:
        raise error_status(error) from error


@router.post("/api/v1/admin/facets/{facet_id}/values", status_code=201)
async def create_facet_value(
    facet_id: uuid.UUID,
    payload: FacetValueInput,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    try:
        return await service(session).create_value(facet_id, payload.model_dump(), actor(principal))
    except (ConflictError, NotFoundError) as error:
        raise error_status(error) from error


@router.patch("/api/v1/admin/facet-values/{value_id}")
async def update_facet_value(
    value_id: uuid.UUID,
    payload: FacetValueInput,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    try:
        return await service(session).update_value(value_id, payload.model_dump(), actor(principal))
    except (NotFoundError, ValidationError) as error:
        raise error_status(error) from error


@router.delete("/api/v1/admin/facet-values/{value_id}", status_code=204)
async def delete_facet_value(
    value_id: uuid.UUID, session: DbSession, principal: AdminPrincipal
) -> None:
    try:
        await service(session).disable_value(value_id, actor(principal))
    except NotFoundError as error:
        raise error_status(error) from error
