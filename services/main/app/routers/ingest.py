"""`/api/v1/ingest` — the endpoint every parser talks to.

Accepts either `application/json` (attachments referenced by URL, downloaded
later by the worker) or `multipart/form-data` with a `payload` field holding
the same JSON plus the files themselves.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from thirdnews_contracts import IngestResult, NewsSubmission

from ..auth import Principal
from ..config import settings
from ..deps import DbSession, IngestPrincipal
from ..ingest_service import create_news
from ..models import ApiKey
from ..schemas import BatchIngestResponse, BatchSubmission

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


async def _api_key_of(session: AsyncSession, principal: Principal) -> ApiKey | None:
    if principal.kind != "api_key":
        return None
    return (
        await session.execute(select(ApiKey).where(ApiKey.id == principal.subject))
    ).scalar_one_or_none()


async def _read_request(
    request: Request,
) -> tuple[NewsSubmission, dict[str, tuple[str | None, bytes, str | None]]]:
    content_type = request.headers.get("content-type", "")
    uploads: dict[str, tuple[str | None, bytes, str | None]] = {}

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        raw = form.get("payload")
        if not isinstance(raw, str):
            raise HTTPException(status_code=422, detail="multipart request needs a `payload` field")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"bad payload json: {exc}") from exc
        for field, value in form.multi_items():
            if field == "payload" or not isinstance(value, UploadFile):
                continue
            content = await value.read()
            if len(content) > settings.max_attachment_bytes:
                raise HTTPException(status_code=413, detail=f"attachment {field} is too large")
            uploads[field] = (value.filename, content, value.content_type)
    else:
        data = await request.json()

    try:
        submission = NewsSubmission.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    return submission, uploads


@router.post("/news", response_model=IngestResult, summary="Submit one news item")
async def add_news(
    request: Request,
    session: DbSession,
    principal: IngestPrincipal,
) -> IngestResult:
    submission, uploads = await _read_request(request)
    api_key = await _api_key_of(session, principal)
    return await create_news(session, submission, api_key=api_key, uploads=uploads)


@router.post("/news/batch", response_model=BatchIngestResponse, summary="Submit many items")
async def add_news_batch(
    payload: BatchSubmission,
    session: DbSession,
    principal: IngestPrincipal,
) -> BatchIngestResponse:
    """URL-only attachments; use the single endpoint when uploading files."""

    api_key = await _api_key_of(session, principal)
    results = [await create_news(session, item, api_key=api_key) for item in payload.items]
    return BatchIngestResponse(results=results)
