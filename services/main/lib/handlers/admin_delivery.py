from uuid import UUID

from fastapi import APIRouter, Query, Request

from lib.core.service_factory import service_factory

from .common import actor
from .dependencies import AdminPrincipal, DbSession

router = APIRouter(prefix="/api/v1/admin/delivery", tags=["delivery"])


@router.get("/dead-letters")
async def dead_letters(
    request: Request,
    principal: AdminPrincipal,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict:
    return await service_factory.dead_letters(request.app.state.settings).list(
        after=after, limit=limit
    )


@router.get("")
async def pending_delivery(
    session: DbSession, principal: AdminPrincipal, limit: int = Query(default=100, ge=1, le=200)
) -> dict:
    return {"items": await service_factory.delivery(session).pending(limit)}


@router.post("/{event_id}/replay", status_code=202)
async def replay_delivery(event_id: UUID, session: DbSession, principal: AdminPrincipal) -> dict:
    available_at = await service_factory.delivery(session).replay(
        event_id,
        actor=actor(principal),
        delay_seconds=service_factory.duplicate_window_seconds() + 1,
    )
    return {"event_id": str(event_id), "available_at": available_at}
