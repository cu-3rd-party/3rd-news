from __future__ import annotations

import json
import uuid
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request

from lib.core.service_factory import service_factory
from lib.dto.requests import (
    ClassifierInput,
    ClassifierPatch,
    ClassifierSigningKeyInput,
)
from lib.infra.clients.http import SafeFetcher, UrlPolicy
from lib.infra.storage.postgres.repositories.classifier_repository import ClassifierRepository
from lib.interactor.errors import ConflictError, NotFoundError, ValidationError

from .common import actor, error_status
from .dependencies import AdminPrincipal, DbSession

router = APIRouter()


def classifier_storage(session: DbSession) -> ClassifierRepository:
    return service_factory.classifier(session)


@router.get("/api/v1/admin/classifiers")
async def classifiers(session: DbSession, principal: AdminPrincipal) -> dict:
    del principal
    return {"items": await classifier_storage(session).list_classifiers()}


def classifier_input_values(payload: ClassifierInput) -> dict:
    values = payload.model_dump(mode="json")
    values["endpoint"] = str(values["endpoint"]).rstrip("/")
    return values


def classifier_patch_values(payload: ClassifierPatch) -> dict:
    values = payload.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    if "endpoint" in values:
        values["endpoint"] = str(values["endpoint"]).rstrip("/")
    return values


@router.post("/api/v1/admin/classifiers", status_code=201)
async def create_classifier(
    payload: ClassifierInput, session: DbSession, principal: AdminPrincipal
) -> dict:
    try:
        return await classifier_storage(session).create_classifier(
            classifier_input_values(payload), actor(principal)
        )
    except ConflictError as error:
        raise error_status(error) from error


@router.patch("/api/v1/admin/classifiers/{classifier_id}")
async def update_classifier(
    classifier_id: uuid.UUID,
    payload: ClassifierPatch,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    try:
        return await classifier_storage(session).update_classifier(
            classifier_id, classifier_patch_values(payload), actor(principal)
        )
    except (NotFoundError, ValidationError) as error:
        raise error_status(error) from error


@router.put("/api/v1/admin/classifiers/{classifier_id}/signing-key")
async def replace_classifier_signing_key(
    classifier_id: uuid.UUID,
    payload: ClassifierSigningKeyInput,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    try:
        return await classifier_storage(session).set_classifier_signing_key(
            classifier_id,
            payload.signing_public_key,
            actor(principal),
        )
    except NotFoundError as error:
        raise error_status(error) from error


@router.delete("/api/v1/admin/classifiers/{classifier_id}/signing-key", status_code=204)
async def clear_classifier_signing_key(
    classifier_id: uuid.UUID,
    session: DbSession,
    principal: AdminPrincipal,
) -> None:
    try:
        await classifier_storage(session).set_classifier_signing_key(
            classifier_id,
            None,
            actor(principal),
        )
    except NotFoundError as error:
        raise error_status(error) from error


@router.delete("/api/v1/admin/classifiers/{classifier_id}", status_code=204)
async def delete_classifier(
    classifier_id: uuid.UUID, session: DbSession, principal: AdminPrincipal
) -> None:
    try:
        await classifier_storage(session).delete_classifier(classifier_id, actor(principal))
    except NotFoundError as error:
        raise error_status(error) from error


@router.post("/api/v1/admin/classifiers/{classifier_id}/probe")
async def probe_classifier(
    classifier_id: uuid.UUID,
    request: Request,
    session: DbSession,
    principal: AdminPrincipal,
) -> dict:
    del principal
    repository = classifier_storage(session)
    try:
        endpoint, timeout_seconds = await repository.classifier_probe_target(classifier_id)
    except NotFoundError as error:
        raise error_status(error) from error
    host = urlsplit(endpoint).hostname
    if not host:
        raise HTTPException(422, "classifier endpoint has no host")
    fetcher = SafeFetcher(
        policy=UrlPolicy.with_service_hosts(
            request.app.state.settings.classifier_service_hosts,
            max_redirects=request.app.state.settings.fetch_max_redirects,
        ),
        timeout_seconds=min(
            timeout_seconds,
            request.app.state.settings.classifier_request_timeout_seconds,
        ),
        max_bytes=request.app.state.settings.classifier_response_max_bytes,
    )
    try:
        result = await fetcher.fetch_bytes(f"{endpoint}/manifest")
        manifest = json.loads(result.body)
    except Exception as error:
        await repository.record_classifier_probe(classifier_id, type(error).__name__)
        return {"ok": False, "error": type(error).__name__}
    await repository.record_classifier_probe(classifier_id, None)
    return {"ok": True, "manifest": manifest}
