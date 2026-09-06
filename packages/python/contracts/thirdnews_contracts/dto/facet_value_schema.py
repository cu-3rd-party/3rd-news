from pydantic import Field

from .contract_model import ContractModel


class FacetValueSchema(ContractModel):
    slug: str
    title: str
    description: str | None = None
    ai_hint: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    match_patterns: list[str] = Field(default_factory=list)
    position: int = 0
