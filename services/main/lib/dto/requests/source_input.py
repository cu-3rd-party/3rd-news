from pydantic import BaseModel, Field, HttpUrl


class SourceInput(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,119}$")
    title: str = Field(min_length=1, max_length=300)
    kind: str = Field(default="other", max_length=64)
    url: HttpUrl | None = None
    description: str | None = None
    enabled: bool = True
    skip_classification: bool = False
    default_labels: dict[str, list[str]] = Field(default_factory=dict)
