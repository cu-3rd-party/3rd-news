from dataclasses import dataclass


@dataclass(frozen=True)
class Transfer:
    origin_id: str
    target_id: str
    source_key: str
    labels: dict[str, list[str]]
