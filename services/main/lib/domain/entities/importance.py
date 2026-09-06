from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Importance:
    urgency: int = 0
    impact: int = 0
    editorial_priority: int = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("urgency", self.urgency),
            ("impact", self.impact),
            ("editorial_priority", self.editorial_priority),
        ):
            if not 0 <= value <= 100:
                raise ValueError(f"{name} must be between 0 and 100")

    @property
    def total(self) -> int:
        return self.urgency + self.impact + self.editorial_priority
