from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class RunResult:
    created: int = 0
    duplicates: int = 0
    skipped: int = 0
    error: str | None = None
    finished_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
