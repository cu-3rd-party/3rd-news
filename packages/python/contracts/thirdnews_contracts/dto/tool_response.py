from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolResponse:
    status_code: int
    body: Any
    text: str

    def json(self) -> Any:
        return self.body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text[:500]}")
