from __future__ import annotations

import uuid
from typing import Any

from lib.interactor.interfaces.storage.taxonomy_repository import TaxonomyRepository


class TaxonomyAdministration:
    def __init__(self, repository: TaxonomyRepository) -> None:
        self.repository = repository

    async def list_facets(self) -> list[dict[str, Any]]:
        return await self.repository.list_facets()

    async def create_facet(self, values: dict[str, Any], actor: str) -> dict[str, Any]:
        return await self.repository.create_facet(values, actor)

    async def update_facet(
        self, facet_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        return await self.repository.update_facet(facet_id, values, actor)

    async def disable_facet(self, facet_id: uuid.UUID, actor: str) -> None:
        await self.repository.disable_facet(facet_id, actor)

    async def create_value(
        self, facet_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        return await self.repository.create_value(facet_id, values, actor)

    async def update_value(
        self, value_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        return await self.repository.update_value(value_id, values, actor)

    async def disable_value(self, value_id: uuid.UUID, actor: str) -> None:
        await self.repository.disable_value(value_id, actor)
