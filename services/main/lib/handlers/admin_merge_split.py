from __future__ import annotations

import uuid

from fastapi import APIRouter

from lib.core.service_factory import service_factory
from lib.dto.requests import (
    MergeInput,
    SplitInput,
)
from lib.interactor.errors import ConflictError, NotFoundError, ValidationError
from lib.interactor.use_cases.news_merge import NewsMerge
from lib.interactor.use_cases.news_split import NewsSplit

from .common import actor, error_status, news_dict
from .dependencies import DbSession, EditorPrincipal

router = APIRouter()


@router.post("/api/v1/admin/news/{news_id}/merge")
async def merge(
    news_id: uuid.UUID, payload: MergeInput, session: DbSession, principal: EditorPrincipal
) -> dict:
    service = NewsMerge(service_factory.news_merge())
    repository = service_factory.news_admin(session)
    try:
        news = await service.get(session, news_id, lock=True)
        await service.merge(session, news, payload.source_ids, actor(principal))
        await repository.commit()
        return await news_dict(session, news, admin=True)
    except (ConflictError, NotFoundError, ValidationError) as error:
        await repository.rollback()
        raise error_status(error) from error


@router.post("/api/v1/admin/news/{news_id}/split")
async def split(
    news_id: uuid.UUID, payload: SplitInput, session: DbSession, principal: EditorPrincipal
) -> dict:
    service = NewsSplit(service_factory.news_split())
    repository = service_factory.news_admin(session)
    try:
        news = await service.get(session, news_id, lock=True)
        created = await service.split(session, news, payload.submission_ids, actor(principal))
        await repository.commit()
        return await news_dict(session, created, admin=True)
    except (ConflictError, NotFoundError, ValidationError) as error:
        await repository.rollback()
        raise error_status(error) from error
