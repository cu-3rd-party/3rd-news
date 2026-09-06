import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Principal:
    kind: str
    subject: str
    display_name: str
    scopes: frozenset[str]
    user_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    role: str | None = None
    filter_preset: dict[str, Any] = field(default_factory=dict)

    def allows(self, *scopes: str) -> bool:
        return "admin" in self.scopes or any(scope in self.scopes for scope in scopes)
