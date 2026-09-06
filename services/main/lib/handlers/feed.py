from __future__ import annotations

import json
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from lib.core.service_factory import service_factory
from lib.interactor.errors.search import SearchError

from .access_policy import enforce_news_access
from .common import news_dict, utc_timestamp
from .dependencies import DbSession, ReadPrincipal

router = APIRouter()


@router.get("/api/v1/feed")
async def feed(
    request: Request,
    session: DbSession,
    principal: ReadPrincipal,
    q: str | None = None,
    source: list[str] | None = None,
    published_from: datetime | None = None,
    published_to: datetime | None = None,
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    has_attachments: bool | None = None,
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    sort_by: str = Query(
        default="published_at",
        alias="sort",
        pattern="^(published_at|received_at|importance|urgency|impact|editorial_priority)$",
    ),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
) -> dict:
    facets: dict[str, list[str]] = {}
    for key in request.query_params:
        if key.startswith("facet."):
            axis = key[6:]
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,119}", axis):
                raise HTTPException(400, "invalid facet filter")
            facets[axis] = [
                part
                for value in request.query_params.getlist(key)
                for part in value.split(",")
                if part
            ]
    preset = principal.filter_preset or {}
    for axis, allowed in (preset.get("facets") or {}).items():
        selected = facets.get(axis) or list(allowed)
        facets[axis] = [value for value in selected if value in set(allowed)]
    requested_sources = list(source or [])
    allowed_sources = list(preset.get("sources") or [])
    if allowed_sources:
        requested_sources = (
            [value for value in requested_sources if value in set(allowed_sources)]
            if requested_sources
            else allowed_sources
        )
    empty_intersection = any(not values for values in facets.values()) or (
        bool(allowed_sources) and not requested_sources
    )
    try:
        offset = int(cursor or 0)
    except ValueError as error:
        raise HTTPException(400, "invalid feed cursor") from error
    if offset < 0:
        raise HTTPException(400, "invalid feed cursor")
    if facets:
        known_axes = await service_factory.news_delivery(session).known_enabled_facets(set(facets))
        if known_axes != set(facets):
            raise HTTPException(400, "unknown facet filter")
    if (
        not principal.allows("editor")
        and not await service_factory.news_delivery(session).visibility_ready()
    ):
        raise HTTPException(503, "search visibility projection is stale")
    if empty_intersection:
        return {"items": [], "next_cursor": None, "total": 0, "facets": {}}
    filter_parts = ['status = "published"']
    for axis, values in facets.items():
        escaped = [json.dumps(value) for value in values]
        filter_parts.append(f"facets.{axis} IN [{','.join(escaped)}]")
    if requested_sources:
        filter_parts.append(
            f"source IN [{','.join(json.dumps(value) for value in requested_sources)}]"
        )
    for field, value, operator in (
        ("published_at_ts", published_from, ">="),
        ("published_at_ts", published_to, "<="),
        ("received_at_ts", received_from, ">="),
        ("received_at_ts", received_to, "<="),
    ):
        if value is not None:
            filter_parts.append(f"{field} {operator} {utc_timestamp(value)}")
    if has_attachments is not None:
        filter_parts.append(f"has_attachments = {str(has_attachments).lower()}")
    sort_field = {
        "published_at": "published_at_ts",
        "received_at": "received_at_ts",
    }.get(sort_by, sort_by)
    try:
        result = await request.app.state.search.search(
            q or "",
            filters=filter_parts,
            facets=["facets.*", "source"],
            sort=[f"{sort_field}:{order}"],
            offset=offset,
            limit=limit,
        )
    except SearchError as error:
        raise HTTPException(503, "search service is unavailable") from error
    ids = [uuid.UUID(str(value["id"])) for value in result.get("hits", [])]
    by_id, projection = await service_factory.news_delivery(session).feed_rows(ids)
    for news_id in ids:
        item = by_id.get(news_id)
        state = projection.get(news_id)
        if item and (state is None or state.visibility_revision < item.visibility_revision):
            raise HTTPException(503, "search visibility projection is stale")
    items = []
    for news_id in ids:
        item = by_id.get(news_id)
        if item is None:
            continue
        try:
            await enforce_news_access(session, item, principal)
        except HTTPException as error:
            if error.status_code == 404:
                continue
            raise
        items.append(await news_dict(session, item))
    estimated_total = int(result.get("estimatedTotalHits", len(items)))
    next_cursor = str(offset + limit) if offset + limit < estimated_total else None
    return {
        "items": items,
        "next_cursor": next_cursor,
        "total": estimated_total,
        "facets": result.get("facetDistribution", {}),
    }
