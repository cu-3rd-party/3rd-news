from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ClassifierInput(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,119}$")
    name: str = Field(min_length=1, max_length=300)
    endpoint: HttpUrl
    allowed_axes: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    signing_public_key: str | None = None
    enabled: bool = True
    shadow: bool = False
    priority: int = 100
    min_confidence: float = Field(default=0.5, ge=0, le=1)
    timeout_seconds: float = Field(default=30, gt=0, le=300)
