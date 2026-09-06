from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Record:
    id: str
    body_md: str
    source_key: str | None = None
    title: str | None = None
    source_text: str | None = None
    source_link: str | None = None
    published_at: datetime | None = None
    attachments: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    labels: dict[str, list[str]] = field(default_factory=dict)
    manual_facets: list[str] = field(default_factory=list)
    is_gold: bool = False

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body_md}" if self.title else self.body_md
