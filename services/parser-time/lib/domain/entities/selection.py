from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Selection:
    team: str
    channel: str
    display_name: str | None = None
    authors: str = "privileged"
    added_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def slug(self) -> str:
        return f"time-{self.team}-{self.channel}"

    @property
    def key(self) -> str:
        return f"{self.team}/{self.channel}"
