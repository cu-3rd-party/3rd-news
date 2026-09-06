from pydantic import BaseModel, Field


class FacetValueInput(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,119}$")
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    ai_hint: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    match_patterns: list[str] = Field(default_factory=list)
    enabled: bool = True
    position: int = 0
