from __future__ import annotations

import uuid

from fastapi import APIRouter

from lib.core.service_factory import service_factory
from lib.dto.requests import (
    LabelsInput,
)
from lib.interactor.errors import NotFoundError, ValidationError

from .common import actor, error_status
from .dependencies import DbSession, EditorPrincipal

router = APIRouter()


@router.put("/api/v1/admin/news/{news_id}/labels")
async def manual_labels(
    news_id: uuid.UUID, payload: LabelsInput, session: DbSession, principal: EditorPrincipal
) -> dict:
    try:
        return await service_factory.news_admin(session).manual_labels(
            news_id,
            labels=payload.labels,
            release_facets=payload.release_facets,
            user_id=principal.user_id,
            actor=actor(principal),
        )
    except (NotFoundError, ValidationError) as error:
        raise error_status(error) from error
