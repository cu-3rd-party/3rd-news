from pydantic import Field

from .contract_model import ContractModel
from .facet_type import FacetType
from .facet_value_schema import FacetValueSchema


class FacetSchema(ContractModel):
    slug: str
    title: str
    description: str | None = None
    ai_hint: str | None = None
    type: FacetType = FacetType.SINGLE
    required: bool = False
    position: int = 0
    values: list[FacetValueSchema] = Field(default_factory=list)
