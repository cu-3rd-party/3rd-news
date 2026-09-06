from __future__ import annotations

import uuid
from typing import Any, Protocol


class TaxonomyRepository(Protocol):
    async def list_facets(self) -> list[dict[str, Any]]: ...

    async def create_facet(self, values: dict[str, Any], actor: str) -> dict[str, Any]: ...

    async def update_facet(
        self, facet_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]: ...

    async def disable_facet(self, facet_id: uuid.UUID, actor: str) -> None: ...

    async def create_value(
        self, facet_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]: ...

    async def update_value(
        self, value_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]: ...

    async def disable_value(self, value_id: uuid.UUID, actor: str) -> None: ...
