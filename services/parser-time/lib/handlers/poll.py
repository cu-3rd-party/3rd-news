from fastapi import APIRouter, Query

from ..dto.poll_out import PollOut
from ..interactor.interfaces.clients.parser_application import ParserApplication
from .common import parse_ref, resources_from


def create_router(holder: list[ParserApplication]) -> APIRouter:
    router = APIRouter()

    @router.post("/poll", response_model=PollOut)
    async def poll_now(
        channel: str | None = None,
        max_age_days: int | None = Query(default=None, ge=1),
        max_pages: int | None = Query(default=None, ge=1, le=100),
    ) -> PollOut:
        resources = resources_from(holder)
        only = parse_ref(channel) if channel else None
        results = await resources.poll(only, max_age_days=max_age_days, max_pages=max_pages)
        return PollOut(ran=len(results), results=results)

    return router
