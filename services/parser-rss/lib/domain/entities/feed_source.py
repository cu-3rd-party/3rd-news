from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeedSource:
    source: str
    url: str
