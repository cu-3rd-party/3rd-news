"""What a client reads from the delivery endpoint (`GET /api/v1/news`)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Attachment(BaseModel):
    id: str
    kind: str
    url: str | None = None
    filename: str | None = None
    mime: str | None = None
    size: int | None = None
    caption: str | None = None
    position: int = 0


class Label(BaseModel):
    facet: str
    facet_title: str | None = None
    value: str
    value_title: str | None = None
    origin: str = "manual"
    confidence: float | None = None


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
    extra: dict = Field(default_factory=dict)


class NewsPage(BaseModel):
    items: list[NewsItem]
    #: Opaque; pass back as `?cursor=` to get the next page.
    next_cursor: str | None = None
    total: int | None = None
