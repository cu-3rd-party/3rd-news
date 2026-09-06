from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .attachment import Attachment
from .label import Label


class NewsItem(BaseModel):
    id: str
    title: str | None = None
    body_md: str
    source_key: str | None = None
    source_link: str | None = None
    source_text: str | None = None
    published_at: datetime | None = None
    received_at: datetime
    lang: str | None = None
    status: str
    labels: list[Label] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
