from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from lib.core.service_factory import service_factory
from lib.dto.principal import Principal
from lib.interactor.errors import NotFoundError

from .access_policy import enforce_news_access, enforce_visibility_barrier
from .dependencies import DbSession, ReadPrincipal

router = APIRouter()


async def media_response(
    attachment_id: uuid.UUID,
    request: Request,
    session,
    principal: Principal,
    *,
    head: bool,
):
    await enforce_visibility_barrier(session, principal)
    try:
        attachment, news = await service_factory.news_delivery(session).attachment_with_news(
            attachment_id
        )
    except NotFoundError as error:
        raise HTTPException(404, str(error)) from error
    await enforce_news_access(session, news, principal)
    metadata = await request.app.state.storage.stat(attachment.object_key)
    headers = {
        "Content-Length": str(metadata.size),
        "Content-Type": metadata.content_type,
        "Accept-Ranges": "bytes",
        "Content-Disposition": request.app.state.storage.content_disposition(attachment.filename),
    }
    if head:
        return Response(status_code=200, headers=headers)
    from lib.infra.storage.s3 import parse_range_header

    try:
        byte_range = parse_range_header(request.headers.get("range"), metadata.size)
    except ValueError as error:
        raise HTTPException(
            416, "range is not satisfiable", headers={"Content-Range": f"bytes */{metadata.size}"}
        ) from error
    if byte_range:
        headers["Content-Length"] = str(byte_range.length)
        headers["Content-Range"] = byte_range.content_range
    return StreamingResponse(
        request.app.state.storage.iter_object(attachment.object_key, byte_range=byte_range),
        headers=headers,
        media_type=metadata.content_type,
        status_code=206 if byte_range else 200,
    )


@router.get("/api/v1/media/{attachment_id}", operation_id="get_media")
async def get_media(
    attachment_id: uuid.UUID, request: Request, session: DbSession, principal: ReadPrincipal
):
    return await media_response(attachment_id, request, session, principal, head=False)


@router.head("/api/v1/media/{attachment_id}", operation_id="head_media")
async def head_media(
    attachment_id: uuid.UUID, request: Request, session: DbSession, principal: ReadPrincipal
):
    return await media_response(attachment_id, request, session, principal, head=True)
