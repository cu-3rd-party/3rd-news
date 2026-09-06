from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    id: str
    subject: str
    payload: Mapping[str, Any]
    deliveries: int
