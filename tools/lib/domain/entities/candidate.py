from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    id: str
    source_key: str
    author: str
    text: str
    reasons: tuple[str, ...]
