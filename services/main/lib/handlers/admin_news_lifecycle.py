from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request
from thirdnews_contracts import (
    NewsSubmission,
)

from lib.core.service_factory import service_factory
from lib.domain import NewsState
from lib.dto.requests import (
    AdminNewsCreate,
    NewsEdit,
)
from lib.interactor.errors import ConflictError, NotFoundError, ValidationError
from lib.interactor.use_cases.news_lifecycle import NewsLifecycle

from .common import actor, audit, error_status, news_dict
from .dependencies import DbSession, EditorPrincipal
from .submissions import ingest_service

router = APIRouter()


@router.get("/api/v1/admin/stats")
async def admin_stats(session: DbSession, principal: EditorPrincipal) -> dict:
    del principal
    return await service_factory.news_admin(session).stats()


@router.get("/api/v1/admin/news")
async def admin_news_list(
    session: DbSession,
    principal: EditorPrincipal,
    status: list[str] | None = None,
    q: str | None = None,
    gold: bool | None = None,
    source: str | None = None,
    unlabelled_facet: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    del principal
    try:
        items, total = await service_factory.news_admin(session).list_news(
            statuses=status,
            query_text=q,
            gold=gold,
            source=source,
            unlabelled_facet=unlabelled_facet,
            limit=limit,
            offset=offset,
        )
    except ValidationError as error:
        raise error_status(error) from error
    return {"items": items, "total": total}


@router.post("/api/v1/admin/news", status_code=201)
async def admin_news_create(
    payload: AdminNewsCreate, request: Request, principal: EditorPrincipal
) -> dict:
    submission_payload = NewsSubmission(
        idempotency_key=payload.idempotency_key,
        title=payload.title,
        body_md=payload.body_md,
        source_link=payload.source_link,
        source_text=payload.source_text,
        published_at=payload.published_at,
        lang=payload.language,
        extra=payload.extra,
    )
    try:
        accepted = await ingest_service(request).execute(
            submission_payload, principal_id=actor(principal)
        )
    except (ConflictError, ValidationError) as error:
        raise error_status(error) from error
    async with request.app.state.database.session_factory() as session:
        try:
            return await service_factory.news_admin(session).news_for_submission(
                accepted.submission_id
            )
        except NotFoundError as error:
            raise error_status(error) from error


@router.get("/api/v1/admin/news/{news_id}")
async def admin_news_get(
    news_id: uuid.UUID, session: DbSession, principal: EditorPrincipal
) -> dict:
    del principal
    try:
        return await service_factory.news_admin(session).news(news_id)
    except NotFoundError as error:
        raise error_status(error) from error


@router.patch("/api/v1/admin/news/{news_id}")
async def admin_news_edit(
    news_id: uuid.UUID, payload: NewsEdit, session: DbSession, principal: EditorPrincipal
) -> dict:
    service = NewsLifecycle(service_factory.news_lifecycle())
    repository = service_factory.news_admin(session)
    try:
        news = await service.get(session, news_id, lock=True)
        values = payload.model_dump(exclude_unset=True, mode="json")
        if "source_link" in values and values["source_link"] is not None:
            values["source_link"] = str(values["source_link"])
        await service.edit(session, news, values, actor(principal))
        await audit(session, principal, "edit", "news", news_id, values)
        await repository.commit()
        return await news_dict(session, news, admin=True)
    except (ConflictError, NotFoundError, ValidationError) as error:
        await repository.rollback()
        raise error_status(error) from error


async def transition(news_id, target, session, principal):
    service = NewsLifecycle(service_factory.news_lifecycle())
    repository = service_factory.news_admin(session)
    try:
        news = await service.get(session, news_id, lock=True)
        await service.transition(session, news, target, actor(principal))
        await repository.commit()
        return await news_dict(session, news, admin=True)
    except (ConflictError, NotFoundError, ValidationError) as error:
        await repository.rollback()
        raise error_status(error) from error


@router.post("/api/v1/admin/news/{news_id}/publish")
async def publish(news_id: uuid.UUID, session: DbSession, principal: EditorPrincipal) -> dict:
    return await transition(news_id, NewsState.PUBLISHED, session, principal)


@router.post("/api/v1/admin/news/{news_id}/reject")
async def reject(news_id: uuid.UUID, session: DbSession, principal: EditorPrincipal) -> dict:
    return await transition(news_id, NewsState.REJECTED, session, principal)


@router.delete("/api/v1/admin/news/{news_id}", status_code=204)
async def delete_news(news_id: uuid.UUID, session: DbSession, principal: EditorPrincipal) -> None:
    await transition(news_id, NewsState.DELETED, session, principal)


@router.post("/api/v1/admin/news/{news_id}/reprocess", status_code=202)
async def reprocess(
    news_id: uuid.UUID,
    request: Request,
    session: DbSession,
    principal: EditorPrincipal,
) -> dict:
    service = NewsLifecycle(service_factory.news_lifecycle(request.app.state.settings.max_attempts))
    repository = service_factory.news_admin(session)
    try:
        news = await service.get(session, news_id, lock=True)
        job = await service.reprocess(session, news, actor(principal))
        await repository.commit()
        return {"job_id": str(job.id), "status": job.status}
    except (ConflictError, NotFoundError, ValidationError) as error:
        raise error_status(error) from error
