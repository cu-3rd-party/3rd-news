import uuid
from typing import Any, Protocol


class SourceStorage(Protocol):
    async def list_sources(self) -> list[dict[str, Any]]: ...

    async def create_source(self, values: dict[str, Any], actor: str) -> dict[str, Any]: ...

    async def update_source(
        self, source_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]: ...
