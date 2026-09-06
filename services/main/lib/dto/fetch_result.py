from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status: int
    content_type: str | None
    content_length: int
    body: bytes
