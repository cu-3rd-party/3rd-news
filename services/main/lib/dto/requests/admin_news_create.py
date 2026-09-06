import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class AdminNewsCreate(BaseModel):
    title: str | None = Field(default=None, max_length=1000)
    body_md: str = Field(max_length=2_000_000)
    source_link: HttpUrl | None = None
    source_text: str = Field(default="Manual", max_length=1000)
    published_at: datetime | None = None
    language: str | None = Field(default=None, min_length=2, max_length=35)
    extra: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))
