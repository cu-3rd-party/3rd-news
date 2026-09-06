from dataclasses import dataclass
from typing import Any


@dataclass
class Patch:
    id: str
    label: str
    changed: dict[str, Any]
    payload: dict[str, Any]
