import uuid
from typing import Any, Protocol


class ApiKeyStorage(Protocol):
    async def list_api_keys(self) -> list[dict[str, Any]]: ...

    async def create_api_key(self, values: dict[str, Any], actor: str) -> dict[str, Any]: ...

    async def revoke_api_key(self, key_id: uuid.UUID, actor: str) -> dict[str, Any]: ...
