from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NormalizedLabel:
    axis: str
    value: str
    confidence: float
    reason: str | None
    evidence: tuple[Mapping[str, Any], ...]
