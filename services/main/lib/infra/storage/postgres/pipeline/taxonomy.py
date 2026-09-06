from __future__ import annotations

from lib.domain import AxisDefinition
from lib.infra.storage.postgres.models import Facet, Setting
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from thirdnews_contracts import FacetSchema, FacetType, FacetValueSchema, Taxonomy


class PipelineTaxonomy:
    async def load(self, session: AsyncSession) -> tuple[Taxonomy, dict[str, AxisDefinition]]:
        facets = (
            (
                await session.scalars(
                    select(Facet)
                    .where(Facet.enabled.is_(True))
                    .options(selectinload(Facet.values))
                    .order_by(Facet.position, Facet.slug)
                )
            )
            .unique()
            .all()
        )
        contract_facets: list[FacetSchema] = []
        definitions: dict[str, AxisDefinition] = {}
        for facet in facets:
            values = sorted(
                (value for value in facet.values if value.enabled),
                key=lambda value: (value.position, value.slug),
            )
            contract_facets.append(
                FacetSchema(
                    slug=facet.slug,
                    title=facet.title,
                    description=facet.description,
                    ai_hint=facet.ai_hint,
                    type=FacetType.MULTI if facet.kind == "multi" else FacetType.SINGLE,
                    required=facet.required,
                    position=facet.position,
                    values=[
                        FacetValueSchema(
                            slug=value.slug,
                            title=value.title,
                            description=value.description,
                            ai_hint=value.ai_hint,
                            synonyms=value.synonyms,
                            match_patterns=value.match_patterns,
                            position=value.position,
                        )
                        for value in values
                    ],
                )
            )
            definitions[facet.slug] = AxisDefinition(
                facet.slug,
                frozenset(value.slug for value in values),
                multiple=facet.kind == "multi",
            )
        revision = await session.get(Setting, "taxonomy_revision")
        version = str((revision.value or {}).get("revision") or 0) if revision else "0"
        return Taxonomy(version=version, facets=contract_facets), definitions
