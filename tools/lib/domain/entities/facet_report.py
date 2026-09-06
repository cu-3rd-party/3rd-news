from dataclasses import dataclass, field


@dataclass(slots=True)
class FacetReport:
    facet: str
    type: str
    n: int
    exact: float
    macro_f1: float
    per_value: dict[str, dict[str, float]] = field(default_factory=dict)
