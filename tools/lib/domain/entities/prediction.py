from dataclasses import dataclass, field


@dataclass(slots=True)
class Prediction:
    labels: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False
