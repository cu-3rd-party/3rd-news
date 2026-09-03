"""`/api/v1/admin/facets` — the screen where new classification axes are born.

Adding "поток 2027" or a whole new axis is a couple of POSTs here; no code,
no migration, and every classifier sees it on its next request.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import audit
from ..deps import AdminPrincipal, DbSession, EditorPrincipal
from ..labels import recompute_effective
from ..models import Facet, FacetValue, NewsEffectiveLabel
from ..schemas import FacetIn, FacetOut, FacetValueIn, FacetValueOut

router = APIRouter(prefix="/api/v1/admin", tags=["admin:taxonomy"])


def _value_out(value: FacetValue) -> FacetValueOut:
    return FacetValueOut(
        id=str(value.id),
        slug=value.slug,
        title=value.title,
        description=value.description,
        ai_hint=value.ai_hint,
        synonyms=list(value.synonyms or []),
        match_patterns=list(value.match_patterns or []),
        is_active=value.is_active,
        position=value.position,
    )


def _facet_out(facet: Facet) -> FacetOut:
    return FacetOut(
        id=str(facet.id),
        slug=facet.slug,
        title=facet.title,
        description=facet.description,
        ai_hint=facet.ai_hint,
        type=facet.type,
        required=facet.required,
        is_active=facet.is_active,
        position=facet.position,
        values=[_value_out(value) for value in facet.values],
    )


async def _get_facet(session, facet_id: str) -> Facet:
    facet = (
        await session.execute(
            select(Facet).options(selectinload(Facet.values)).where(Facet.id == facet_id)
        )
    ).scalar_one_or_none()
    if facet is None:
        raise HTTPException(status_code=404, detail="facet not found")
    return facet


@router.get("/facets", response_model=list[FacetOut])
async def list_facets(session: DbSession, principal: EditorPrincipal) -> list[FacetOut]:
    del principal
    facets = (
        (
            await session.execute(
                select(Facet).options(selectinload(Facet.values)).order_by(Facet.position, Facet.slug)
            )
        )
        .scalars()
        .all()
    )
    return [_facet_out(facet) for facet in facets]


@router.post("/facets", response_model=FacetOut, status_code=201)
async def create_facet(payload: FacetIn, session: DbSession, principal: AdminPrincipal) -> FacetOut:
    if payload.type not in {"single", "multi"}:
        raise HTTPException(status_code=422, detail="type must be 'single' or 'multi'")
    slug = slugify(payload.slug or payload.title)[:120]
    if not slug:
        raise HTTPException(status_code=422, detail="cannot derive a slug from the title")
    exists = (await session.execute(select(Facet).where(Facet.slug == slug))).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"facet {slug!r} already exists")

    facet = Facet(
        slug=slug,
        title=payload.title,
        description=payload.description,
        ai_hint=payload.ai_hint,
        type=payload.type,
        required=payload.required,
        is_active=payload.is_active,
        position=payload.position,
    )
    session.add(facet)
    await session.flush()
    await audit.log(session, principal, "create", "facet", str(facet.id), {"slug": slug})
    await session.commit()
    return _facet_out(await _get_facet(session, facet.id))


@router.get("/facets/{facet_id}", response_model=FacetOut)
async def get_facet(facet_id: str, session: DbSession, principal: EditorPrincipal) -> FacetOut:
    del principal
    return _facet_out(await _get_facet(session, facet_id))


@router.patch("/facets/{facet_id}", response_model=FacetOut)
async def update_facet(
    facet_id: str, payload: FacetIn, session: DbSession, principal: AdminPrincipal
) -> FacetOut:
    facet = await _get_facet(session, facet_id)
    facet.title = payload.title
    facet.description = payload.description
    facet.ai_hint = payload.ai_hint
    facet.type = payload.type
    facet.required = payload.required
    facet.is_active = payload.is_active
    facet.position = payload.position
    if payload.slug:
        facet.slug = slugify(payload.slug)[:120]
    await audit.log(session, principal, "update", "facet", facet_id, {"slug": facet.slug})
    await session.commit()
    return _facet_out(await _get_facet(session, facet_id))


@router.delete("/facets/{facet_id}", status_code=204, response_model=None)
async def delete_facet(facet_id: str, session: DbSession, principal: AdminPrincipal) -> None:
    facet = await _get_facet(session, facet_id)
    affected = await _news_carrying_facet(session, facet.id)
    await audit.log(session, principal, "delete", "facet", facet_id, {"slug": facet.slug})
    await session.delete(facet)
    await session.flush()
    for news_id in affected:
        await recompute_effective(session, news_id)
    await session.commit()


async def _news_carrying_facet(session, facet_id) -> list:
    """Items whose effective labels are about to be invalidated."""

    rows = await session.execute(
        select(NewsEffectiveLabel.news_id).where(NewsEffectiveLabel.facet_id == facet_id)
    )
    return list(rows.scalars().all())


@router.post("/facets/{facet_id}/values", response_model=FacetValueOut, status_code=201)
async def create_value(
    facet_id: str, payload: FacetValueIn, session: DbSession, principal: AdminPrincipal
) -> FacetValueOut:
    facet = await _get_facet(session, facet_id)
    slug = slugify(payload.slug or payload.title)[:120]
    if not slug:
        raise HTTPException(status_code=422, detail="cannot derive a slug from the title")
    if any(value.slug == slug for value in facet.values):
        raise HTTPException(status_code=409, detail=f"value {slug!r} already exists in this facet")

    value = FacetValue(
        facet_id=facet.id,
        slug=slug,
        title=payload.title,
        description=payload.description,
        ai_hint=payload.ai_hint,
        synonyms=payload.synonyms,
        match_patterns=payload.match_patterns,
        is_active=payload.is_active,
        position=payload.position,
    )
    session.add(value)
    await session.flush()
    await audit.log(
        session, principal, "create", "facet_value", str(value.id), {"facet": facet.slug, "slug": slug}
    )
    await session.commit()
    return _value_out(value)


@router.patch("/values/{value_id}", response_model=FacetValueOut)
async def update_value(
    value_id: str, payload: FacetValueIn, session: DbSession, principal: AdminPrincipal
) -> FacetValueOut:
    value = (
        await session.execute(select(FacetValue).where(FacetValue.id == value_id))
    ).scalar_one_or_none()
    if value is None:
        raise HTTPException(status_code=404, detail="value not found")

    value.title = payload.title
    value.description = payload.description
    value.ai_hint = payload.ai_hint
    value.synonyms = payload.synonyms
    value.match_patterns = payload.match_patterns
    value.is_active = payload.is_active
    value.position = payload.position
    if payload.slug:
        value.slug = slugify(payload.slug)[:120]

    await audit.log(session, principal, "update", "facet_value", value_id, {"slug": value.slug})
    await session.commit()
    return _value_out(value)


@router.delete("/values/{value_id}", status_code=204, response_model=None)
async def delete_value(value_id: str, session: DbSession, principal: AdminPrincipal) -> None:
    value = (
        await session.execute(select(FacetValue).where(FacetValue.id == value_id))
    ).scalar_one_or_none()
    if value is None:
        raise HTTPException(status_code=404, detail="value not found")

    # Deleting the value cascades its labels away; the items that carried it
    # need their effective labels rebuilt before they are served again.
    affected = (
        (
            await session.execute(
                select(NewsEffectiveLabel.news_id).where(NewsEffectiveLabel.value_id == value.id)
            )
        )
        .scalars()
        .all()
    )
    await audit.log(session, principal, "delete", "facet_value", value_id, {"slug": value.slug})
    await session.delete(value)
    await session.flush()
    for news_id in affected:
        await recompute_effective(session, news_id)
    await session.commit()
