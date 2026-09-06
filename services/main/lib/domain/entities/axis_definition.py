from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AxisDefinition:
    slug: str
    values: frozenset[str]
    multiple: bool = False
