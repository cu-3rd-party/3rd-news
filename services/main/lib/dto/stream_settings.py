from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StreamSettings:
    name: str = "THIRDNEWS"
    subjects: tuple[str, ...] = ("thirdnews.v2.>",)
    max_age_seconds: int = 7 * 24 * 60 * 60
    duplicate_window_seconds: int = 10 * 60
