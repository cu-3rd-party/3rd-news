"""`/api/v1/news` — the single endpoint clients read from.

Filtering by taxonomy uses dynamic parameters, because the facets themselves
are created at runtime:

    GET /api/v1/news?facet.importance=high,medium&facet.stream=2025

Values inside one facet are ORed, different facets are ANDed. Anything the
caller's credential carries in `filter_preset` is ANDed on top and cannot be
widened by the query string.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import Select, exists, false, func, or_, select, tuple_
from sqlalchemy.orm import selectinload
from thirdnews_contracts import Attachment as AttachmentOut
from thirdnews_contracts import Label, NewsItem, NewsPage, Taxonomy

from ..config import settings
from ..deps import DbSession, ReadPrincipal
from ..models import Attachment, Facet, FacetValue, News, NewsEffectiveLabel, Source
from ..storage import public_url
from ..taxonomy import build_taxonomy

router = APIRouter(prefix="/api/v1", tags=["news"])

FACET_PARAM_PREFIX = "facet."
MAX_LIMIT = 200
#: Slug that cannot exist, used to force an empty result set.
NO_MATCH = ["no-match"]


def _sort_expr():
    """Order by publication time, falling back to arrival time."""

    return func.coalesce(News.published_at, News.received_at)


def _encode_cursor(sort_value: datetime, news_id) -> str:
    raw = f"{sort_value.isoformat()}|{news_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding).decode()
        stamp, news_id = raw.split("|", 1)
        return datetime.fromisoformat(stamp), uuid.UUID(news_id)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="malformed cursor") from exc


def _facet_filters(params: dict[str, list[str]]) -> dict[str, list[str]]:
    """Pull `facet.<slug>=a,b` out of the query string."""

    filters: dict[str, list[str]] = {}
    for key, values in params.items():
        if not key.startswith(FACET_PARAM_PREFIX):
            continue
        facet = key[len(FACET_PARAM_PREFIX) :]
        collected: list[str] = []
        for value in values:
            collected.extend(part.strip() for part in value.split(",") if part.strip())
        if collected:
            filters.setdefault(facet, []).extend(collected)
    return filters


def _apply_facets(query: Select, filters: dict[str, list[str]]) -> Select:
    for facet_slug, value_slugs in filters.items():
        if not value_slugs:
            # The caller asked for values their credential does not allow.
            return query.where(false())
        condition = exists(
            select(NewsEffectiveLabel.news_id)
            .join(FacetValue, FacetValue.id == NewsEffectiveLabel.value_id)
            .join(Facet, Facet.id == NewsEffectiveLabel.facet_id)
            .where(
                NewsEffectiveLabel.news_id == News.id,
                Facet.slug == facet_slug,
                FacetValue.slug.in_(value_slugs),
            )
            .correlate(News)
        )
        query = query.where(condition)
    return query


def _merge_filters(
    query_filters: dict[str, list[str]], preset: dict
) -> tuple[dict[str, list[str]], dict]:
    """Intersect the caller's facet filters with what their credential allows."""

    preset_facets: dict[str, list[str]] = preset.get("facets") or {}
    merged = dict(query_filters)
    for facet_slug, allowed in preset_facets.items():
        requested = merged.get(facet_slug)
        if requested:
            narrowed = [value for value in requested if value in allowed]
            # An empty intersection stays empty; `_apply_facets` reads that
            # as "match nothing" — the safe reading of a denied filter.
            merged[facet_slug] = narrowed
        else:
            merged[facet_slug] = list(allowed)
    return merged, preset


def _serialise(news: News) -> NewsItem:
    return NewsItem(
        id=str(news.id),
        title=news.title,
        body_md=news.body_md,
        source_key=news.source.slug if news.source else None,
        source_link=news.source_link,
        source_text=news.source_text,
        published_at=news.published_at,
        received_at=news.received_at,
        lang=news.lang,
        status=news.status,
        labels=[
            Label(
                facet=label.facet.slug,
                facet_title=label.facet.title,
                value=label.value.slug,
                value_title=label.value.title,
                origin=label.origin,
                confidence=label.confidence,
            )
            for label in news.effective_labels
        ],
        attachments=[
            AttachmentOut(
                id=str(item.id),
                kind=item.kind,
                url=public_url(item.storage_path) or item.original_url,
                filename=item.filename,
                mime=item.mime,
                size=item.size,
                caption=item.caption,
                position=item.position,
            )
            for item in news.attachments
        ],
        extra=news.extra or {},
    )


def _loaded(query: Select) -> Select:
    return query.options(
        selectinload(News.attachments),
        selectinload(News.effective_labels).selectinload(NewsEffectiveLabel.facet),
        selectinload(News.effective_labels).selectinload(NewsEffectiveLabel.value),
        selectinload(News.source),
    )


@router.get("/news", response_model=NewsPage, summary="Read news with filters")
async def list_news(
    request: Request,
    session: DbSession,
    principal: ReadPrincipal,
    q: str | None = Query(default=None, description="Substring search over title and body"),
    source: list[str] | None = Query(default=None, description="Source slug, repeatable"),
    status: list[str] | None = Query(default=None, description="Editors only"),
    published_from: datetime | None = None,
    published_to: datetime | None = None,
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    has_attachments: bool | None = None,
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
    with_total: bool = False,
) -> NewsPage:
    params: dict[str, list[str]] = {}
    for key in request.query_params.keys():
        params[key] = request.query_params.getlist(key)
    facet_filters, preset = _merge_filters(_facet_filters(params), principal.filter_preset or {})

    query = select(News)

    allowed_statuses = settings.public_statuses
    if principal.has_scope("editor") or principal.has_scope("admin"):
        allowed_statuses = status or None
    elif status and set(status) - set(allowed_statuses):
        raise HTTPException(status_code=403, detail="not allowed to read these statuses")
    if allowed_statuses:
        query = query.where(News.status.in_(allowed_statuses))

    query = _apply_facets(query, facet_filters)

    sources = list(source or [])
    allowed_sources = preset.get("sources") or []
    if allowed_sources:
        # Same rule as facets: the preset narrows, never widens.
        sources = (
            [slug for slug in sources if slug in allowed_sources]
            if sources
            else list(allowed_sources)
        )
        if not sources:
            query = query.where(false())
    if sources:
        query = query.where(
            News.source_id.in_(select(Source.id).where(Source.slug.in_(sources)))
        )

    if q:
        pattern = f"%{q}%"
        query = query.where(or_(News.title.ilike(pattern), News.body_md.ilike(pattern)))
    if published_from:
        query = query.where(News.published_at >= published_from)
    if published_to:
        query = query.where(News.published_at <= published_to)
    if received_from:
        query = query.where(News.received_at >= received_from)
    if received_to:
        query = query.where(News.received_at <= received_to)
    if has_attachments is not None:
        condition = exists(
            select(Attachment.id).where(Attachment.news_id == News.id).correlate(News)
        )
        query = query.where(condition if has_attachments else ~condition)

    total = None
    if with_total:
        total = (
            await session.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()

    sort_expr = _sort_expr()
    if cursor:
        cursor_stamp, cursor_id = _decode_cursor(cursor)
        if cursor_stamp.tzinfo is None:
            cursor_stamp = cursor_stamp.replace(tzinfo=timezone.utc)
        pair = tuple_(sort_expr, News.id)
        anchor = tuple_(cursor_stamp, cursor_id)
        query = query.where(pair < anchor if order == "desc" else pair > anchor)

    ordering = (
        (sort_expr.desc(), News.id.desc()) if order == "desc" else (sort_expr.asc(), News.id.asc())
    )
    query = _loaded(query).order_by(*ordering).limit(limit + 1)

    rows = (await session.execute(query)).unique().scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor(last.published_at or last.received_at, last.id)

    return NewsPage(
        items=[_serialise(item) for item in rows], next_cursor=next_cursor, total=total
    )


@router.get("/news/{news_id}", response_model=NewsItem, summary="Read one news item")
async def get_news(
    news_id: str,
    session: DbSession,
    principal: ReadPrincipal,
) -> NewsItem:
    row = await session.execute(_loaded(select(News)).where(News.id == news_id))
    news = row.unique().scalar_one_or_none()
    if news is None:
        raise HTTPException(status_code=404, detail="news not found")
    is_editor = principal.has_scope("editor") or principal.has_scope("admin")
    if not is_editor and news.status not in settings.public_statuses:
        raise HTTPException(status_code=404, detail="news not found")
    return _serialise(news)


@router.get("/taxonomy", response_model=Taxonomy, summary="Facets available for filtering")
async def get_taxonomy(session: DbSession, principal: ReadPrincipal) -> Taxonomy:
    """The facets and values a client may filter on."""

    del principal  # authentication only; the taxonomy is the same for everyone
    return await build_taxonomy(session)
