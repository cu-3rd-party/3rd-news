from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from lib.core.service_factory import service_factory
from lib.dto.requests import (
    GoldInput,
)

from .common import actor
from .dependencies import DbSession, EditorPrincipal

router = APIRouter()


@router.get("/api/v1/admin/news/export")
async def export(
    session: DbSession, principal: EditorPrincipal, gold_only: bool = False
) -> StreamingResponse:
    del principal
    rows = await service_factory.news_admin(session).export_news(gold_only=gold_only)

    async def generate():
        for item in rows:
            yield (json.dumps(item, ensure_ascii=False, default=str) + "\n")

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/api/v1/admin/news/gold")
async def gold(payload: GoldInput, session: DbSession, principal: EditorPrincipal) -> dict:
    count = await service_factory.news_admin(session).set_gold(
        payload.ids, payload.is_gold, actor(principal)
    )
    return {"updated": count}
