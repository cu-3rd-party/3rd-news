from dataclasses import dataclass


@dataclass(frozen=True)
class Post:
    id: str
    source_key: str
    published_at: str
    text: str
