import uuid
from typing import Any, Protocol


class EditorialRuleStorage(Protocol):
    async def list_editorial_rules(self) -> list[dict[str, Any]]: ...

    async def create_editorial_rule(self, values: dict[str, Any], actor: str) -> dict[str, Any]: ...

    async def revise_editorial_rule(
        self, rule_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]: ...

    async def disable_editorial_rule(self, rule_id: uuid.UUID, actor: str) -> None: ...
