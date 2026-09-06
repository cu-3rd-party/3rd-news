from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator


class ClassifierPatch(BaseModel):
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,119}$")
    name: str | None = Field(default=None, min_length=1, max_length=300)
    endpoint: HttpUrl | None = None
    allowed_axes: list[str] | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    shadow: bool | None = None
    priority: int | None = None
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    timeout_seconds: float | None = Field(default=None, gt=0, le=300)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> ClassifierPatch:
        nulls = [name for name in self.model_fields_set if getattr(self, name) is None]
        if nulls:
            raise ValueError(f"classifier fields cannot be null: {sorted(nulls)}")
        return self
