from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ApiKeyInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(default_factory=lambda: ["read"])
    source_id: uuid.UUID | None = None
    filter_preset: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_filter_preset(self) -> ApiKeyInput:
        unknown = self.filter_preset.keys() - {"sources", "facets"}
        if unknown:
            raise ValueError(f"unknown filter preset fields: {', '.join(sorted(unknown))}")
        sources = self.filter_preset.get("sources", [])
        facets = self.filter_preset.get("facets", {})
        if not isinstance(sources, list) or not all(isinstance(item, str) for item in sources):
            raise ValueError("filter preset sources must be a list of strings")
        if not isinstance(facets, dict) or not all(
            isinstance(axis, str)
            and isinstance(values, list)
            and all(isinstance(value, str) for value in values)
            for axis, values in facets.items()
        ):
            raise ValueError("filter preset facets must map strings to lists of strings")
        return self
