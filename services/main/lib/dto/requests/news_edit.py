from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator


class NewsEdit(BaseModel):
    title: str | None = Field(default=None, max_length=1000)
    body_md: str | None = Field(default=None, max_length=2_000_000)
    source_link: HttpUrl | None = None
    source_text: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, min_length=2, max_length=35)
    source_published_at: datetime | None = None
    extra: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_for_required_storage_fields(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for field in ("body_md", "extra"):
                if field in value and value[field] is None:
                    raise ValueError(f"{field} cannot be null")
        return value
