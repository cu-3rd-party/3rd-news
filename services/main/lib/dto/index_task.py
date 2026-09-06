from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class IndexTask:
    uid: int
    status: str
    error: Mapping[str, Any] | None = None
