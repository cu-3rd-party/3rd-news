from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    key: str
    size: int
    content_type: str
    sha256: str
    metadata: Mapping[str, str]
