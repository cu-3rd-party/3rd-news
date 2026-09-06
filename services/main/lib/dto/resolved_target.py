from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    host: str
    port: int
    addresses: tuple[str, ...]
