from typing import Any

from fastapi import HTTPException

from lib.core.service_factory import service_factory
from lib.infra.clients.auth import Principal
from lib.interactor.errors import NotFoundError


async def enforce_news_access(session: Any, news: Any, principal: Principal) -> None:
    try:
        await service_factory.news_delivery(session).enforce_access(
            news,
            editor=principal.allows("editor"),
            preset=principal.filter_preset or {},
        )
    except NotFoundError as error:
        raise HTTPException(404, str(error)) from error


async def enforce_visibility_barrier(session: Any, principal: Principal) -> None:
    if principal.allows("editor"):
        return
    if not await service_factory.news_delivery(session).visibility_ready():
        raise HTTPException(503, "visibility materialization is stale")
