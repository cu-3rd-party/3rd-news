"""Serialising the stored taxonomy into the shape classifiers receive."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from thirdnews_contracts import FacetSchema, FacetValueSchema, Taxonomy

from .models import Facet


async def build_taxonomy(
    session: AsyncSession, only_facets: list[str] | None = None
) -> Taxonomy:
    query = (
        select(Facet)
        .options(selectinload(Facet.values))
        .where(Facet.is_active.is_(True))
        .order_by(Facet.position, Facet.slug)
    )
    if only_facets:
        query = query.where(Facet.slug.in_(only_facets))

    facets = (await session.execute(query)).scalars().all()
    return Taxonomy(
        facets=[
            FacetSchema(
                slug=facet.slug,
                title=facet.title,
                description=facet.description,
                ai_hint=facet.ai_hint,
                type=facet.type,
                required=facet.required,
                position=facet.position,
                values=[
                    FacetValueSchema(
                        slug=value.slug,
                        title=value.title,
                        description=value.description,
                        ai_hint=value.ai_hint,
                        synonyms=list(value.synonyms or []),
                        match_patterns=list(value.match_patterns or []),
                        position=value.position,
                    )
                    for value in facet.values
                    if value.is_active
                ],
            )
            for facet in facets
        ]
    )
