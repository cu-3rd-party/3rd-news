"""`/api/v1/classification/callback` — where slow classifiers post their answer.

A classifier that cannot answer inside the request (an LLM, a queue of its
own) replies `202 Accepted` and later calls this endpoint with the same
`request_id`, signed with the same shared secret.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from thirdnews_contracts import CallbackResult, verify_signature

from ..deps import DbSession
from ..dispatcher import apply_result, finish_if_settled
from ..models import ClassificationJob

router = APIRouter(prefix="/api/v1/classification", tags=["classification"])


@router.post("/callback", status_code=202, summary="Deliver a delayed classification")
async def classification_callback(
    request: Request,
    session: DbSession,
    x_3rdnews_signature: str | None = Header(default=None),
    x_3rdnews_timestamp: str | None = Header(default=None),
) -> dict:
    raw = await request.body()
    try:
        payload = CallbackResult.model_validate_json(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"bad callback body: {exc}") from exc

    job = (
        await session.execute(
            select(ClassificationJob)
            .options(selectinload(ClassificationJob.classifier))
            .where(ClassificationJob.id == payload.request_id)
        )
    ).scalar_one_or_none()
    if job is None or job.classifier is None:
        raise HTTPException(status_code=404, detail="unknown request_id")

    classifier = job.classifier
    if classifier.secret and not verify_signature(
        classifier.secret, raw, x_3rdnews_signature, x_3rdnews_timestamp
    ):
        raise HTTPException(status_code=401, detail="bad signature")
    if payload.classifier != classifier.slug:
        raise HTTPException(status_code=403, detail="callback does not match this job")
    if job.status == "done":
        # Late duplicate; the first answer stands.
        return {"status": "already_recorded"}

    if payload.error:
        job.status = "failed"
        job.error = payload.error[:2000]
        await session.commit()
        # A refusal still settles the item: nobody else is going to answer.
        await finish_if_settled(session, job.news_id)
        return {"status": "recorded_error"}

    await apply_result(session, job, classifier, payload.labels, meta=payload.meta)
    return {"status": "recorded"}
