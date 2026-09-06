from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    url: str
    key: str
    headers: Mapping[str, str]
    expires_in: int
