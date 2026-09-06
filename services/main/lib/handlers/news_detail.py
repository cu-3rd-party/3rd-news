from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from lib.core.service_factory import service_factory
from lib.interactor.errors import NotFoundError

from .access_policy import enforce_news_access, enforce_visibility_barrier
from .common import news_dict
from .dependencies import DbSession, ReadPrincipal

router = APIRouter()


@router.get("/api/v1/news/{news_id}")
async def get_news(news_id: uuid.UUID, session: DbSession, principal: ReadPrincipal) -> dict:
    await enforce_visibility_barrier(session, principal)
    try:
        news = await service_factory.news_delivery(session).news(news_id)
    except NotFoundError as error:
        raise HTTPException(404, str(error)) from error
    await enforce_news_access(session, news, principal)
    return await news_dict(session, news, admin=principal.allows("editor"))


@router.get("/api/v1/taxonomy")
async def taxonomy(session: DbSession, principal: ReadPrincipal) -> dict:
    del principal
    return await service_factory.news_delivery(session).taxonomy()
