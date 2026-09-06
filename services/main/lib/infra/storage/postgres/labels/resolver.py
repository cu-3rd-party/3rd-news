from __future__ import annotations

from typing import Any

from lib.infra.storage.postgres.models import Facet, FacetValue
from lib.interactor.errors import ValidationError
from sqlalchemy import select


class LabelResolver:
    async def resolve(
        self, session: Any, labels: dict[str, list[str]]
    ) -> dict[str, tuple[Facet, list[FacetValue]]]:
        result = {}
        for facet_slug, value_slugs in labels.items():
            facet = (
                await session.execute(
                    select(Facet).where(Facet.slug == facet_slug, Facet.enabled.is_(True))
                )
            ).scalar_one_or_none()
            if facet is None:
                raise ValidationError(f"unknown facet: {facet_slug}")
            values = (
                (
                    await session.execute(
                        select(FacetValue).where(
                            FacetValue.facet_id == facet.id,
                            FacetValue.slug.in_(value_slugs),
                            FacetValue.enabled.is_(True),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if len(values) != len(set(value_slugs)):
                raise ValidationError(f"unknown value for facet: {facet_slug}")
            if facet.kind == "single" and len(values) > 1:
                raise ValidationError(f"facet {facet_slug} accepts one value")
            result[facet_slug] = facet, values
        return result
