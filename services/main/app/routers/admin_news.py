"""`/api/v1/admin/news` — the review queue and manual classification."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from .. import audit
from ..deps import AdminPrincipal, DbSession, EditorPrincipal
from ..ingest_service import enqueue_jobs, schedule_classification
from ..labels import recompute_effective, set_manual_labels
from ..models import Facet, News, NewsEffectiveLabel, NewsLabel, Source
from ..schemas import (
    LabelOpinion,
    ManualLabelsIn,
    NewsAdminDetail,
    NewsEditIn,
    NewsStatusIn,
)
from ..storage import public_url

router = APIRouter(prefix="/api/v1/admin/news", tags=["admin:news"])

STATUSES = {"pending", "needs_review", "classified", "published", "rejected", "archived"}


def _detail(news: News) -> NewsAdminDetail:
    effective: dict[str, list[str]] = {}
    for label in news.effective_labels:
        effective.setdefault(label.facet.slug, []).append(label.value.slug)

    return NewsAdminDetail(
        id=str(news.id),
        title=news.title,
        body_md=news.body_md,
        source_key=news.source.slug if news.source else None,
        source_link=news.source_link,
        source_text=news.source_text,
        published_at=news.published_at,
        received_at=news.received_at,
        status=news.status,
        lang=news.lang,
        extra=news.extra or {},
        manual_facets=list(news.manual_facets or []),
        classified_at=news.classified_at,
        attachments=[
            {
                "id": str(item.id),
                "kind": item.kind,
                "url": public_url(item.storage_path) or item.original_url,
                "filename": item.filename,
                "mime": item.mime,
                "size": item.size,
                "status": item.status,
                "caption": item.caption,
            }
            for item in news.attachments
        ],
        effective=effective,
        opinions=[
            LabelOpinion(
                facet=label.facet.slug,
                value=label.value.slug,
                origin=label.origin,
                origin_key=label.origin_key,
                confidence=label.confidence,
                reason=label.reason,
                created_at=label.created_at,
            )
            for label in news.labels
        ],
    )


def _detail_query():
    return select(News).options(
        selectinload(News.attachments),
        selectinload(News.source),
        selectinload(News.effective_labels).selectinload(NewsEffectiveLabel.facet),
        selectinload(News.effective_labels).selectinload(NewsEffectiveLabel.value),
        selectinload(News.labels).selectinload(NewsLabel.facet),
        selectinload(News.labels).selectinload(NewsLabel.value),
    )


async def _get_news(session, news_id: str) -> News:
    result = await session.execute(_detail_query().where(News.id == news_id))
    news = result.unique().scalar_one_or_none()
    if news is None:
        raise HTTPException(status_code=404, detail="news not found")
    return news


@router.get("", response_model=dict, summary="Review queue")
async def list_news(
    session: DbSession,
    principal: EditorPrincipal,
    status: list[str] | None = Query(default=None),
    source: str | None = None,
    q: str | None = None,
    unlabelled_facet: str | None = Query(
        default=None, description="Only items with no effective value for this facet"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    del principal
    query = _detail_query()
    count_query = select(func.count()).select_from(News)

    if status:
        query = query.where(News.status.in_(status))
        count_query = count_query.where(News.status.in_(status))
    if source:
        subquery = select(Source.id).where(Source.slug == source)
        query = query.where(News.source_id.in_(subquery))
        count_query = count_query.where(News.source_id.in_(subquery))
    if q:
        pattern = f"%{q}%"
        query = query.where(News.title.ilike(pattern) | News.body_md.ilike(pattern))
        count_query = count_query.where(News.title.ilike(pattern) | News.body_md.ilike(pattern))
    if unlabelled_facet:
        labelled = (
            select(NewsEffectiveLabel.news_id)
            .join(Facet, Facet.id == NewsEffectiveLabel.facet_id)
            .where(Facet.slug == unlabelled_facet)
        )
        query = query.where(~News.id.in_(labelled))
        count_query = count_query.where(~News.id.in_(labelled))

    total = (await session.execute(count_query)).scalar_one()
    query = query.order_by(News.received_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(query)).unique().scalars().all()
    return {"items": [_detail(item) for item in rows], "total": total}


@router.get("/{news_id}", response_model=NewsAdminDetail)
async def get_news(news_id: str, session: DbSession, principal: EditorPrincipal) -> NewsAdminDetail:
    del principal
    return _detail(await _get_news(session, news_id))


@router.put("/{news_id}/labels", response_model=NewsAdminDetail, summary="Classify by hand")
async def set_labels(
    news_id: str, payload: ManualLabelsIn, session: DbSession, principal: EditorPrincipal
) -> NewsAdminDetail:
    news = await _get_news(session, news_id)
    user_id = uuid.UUID(principal.user_id) if principal.user_id else None
    try:
        await set_manual_labels(
            session, news, payload.labels, payload.release_facets, user_id=user_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await audit.log(
        session, principal, "label", "news", news_id, {"labels": payload.labels}
    )
    await session.commit()
    return _detail(await _get_news(session, news_id))


@router.patch("/{news_id}", response_model=NewsAdminDetail, summary="Edit the text of an item")
async def edit_news(
    news_id: str, payload: NewsEditIn, session: DbSession, principal: EditorPrincipal
) -> NewsAdminDetail:
    news = await _get_news(session, news_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(news, field, value)
    await audit.log(
        session, principal, "edit", "news", news_id, payload.model_dump(exclude_unset=True, mode="json")
    )
    await session.commit()
    return _detail(await _get_news(session, news_id))


@router.post("/{news_id}/status", response_model=NewsAdminDetail)
async def set_status(
    news_id: str, payload: NewsStatusIn, session: DbSession, principal: EditorPrincipal
) -> NewsAdminDetail:
    if payload.status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(STATUSES)}")
    news = await _get_news(session, news_id)
    news.status = payload.status
    await audit.log(session, principal, "status", "news", news_id, {"status": payload.status})
    await session.commit()
    return _detail(await _get_news(session, news_id))


@router.post("/{news_id}/reclassify", response_model=NewsAdminDetail)
async def reclassify(
    news_id: str,
    session: DbSession,
    principal: EditorPrincipal,
    classifier_id: str | None = None,
) -> NewsAdminDetail:
    """Re-run the classifiers, e.g. after editing the taxonomy or a prompt."""

    news = await _get_news(session, news_id)
    news.classified_at = None
    jobs = await schedule_classification(session, news, only_classifier_id=classifier_id)
    await audit.log(
        session, principal, "reclassify", "news", news_id, {"classifier_id": classifier_id}
    )
    await session.commit()
    await enqueue_jobs(jobs)
    return _detail(await _get_news(session, news_id))


@router.post("/{news_id}/recompute", response_model=NewsAdminDetail)
async def recompute(
    news_id: str, session: DbSession, principal: EditorPrincipal
) -> NewsAdminDetail:
    """Rebuild effective labels from the stored opinions, without re-asking."""

    del principal
    news = await _get_news(session, news_id)
    await recompute_effective(session, news.id)
    await session.commit()
    return _detail(await _get_news(session, news_id))


@router.delete("/{news_id}", status_code=204, response_model=None)
async def delete_news(news_id: str, session: DbSession, principal: AdminPrincipal) -> None:
    news = await _get_news(session, news_id)
    await audit.log(session, principal, "delete", "news", news_id, {})
    await session.delete(news)
    await session.commit()


@router.get("/{news_id}/timeline", response_model=list[LabelOpinion])
async def timeline(
    news_id: str, session: DbSession, principal: EditorPrincipal
) -> list[LabelOpinion]:
    """Every opinion ever recorded about this item, newest first."""

    del principal
    news = await _get_news(session, news_id)
    ordered = sorted(news.labels, key=lambda label: label.created_at, reverse=True)
    return [
        LabelOpinion(
            facet=label.facet.slug,
            value=label.value.slug,
            origin=label.origin,
            origin_key=label.origin_key,
            confidence=label.confidence,
            reason=label.reason,
            created_at=label.created_at,
        )
        for label in ordered
    ]
