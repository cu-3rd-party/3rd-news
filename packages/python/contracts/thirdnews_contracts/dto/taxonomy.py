from pydantic import Field

from .contract_model import ContractModel
from .facet_schema import FacetSchema


class Taxonomy(ContractModel):
    version: str
    facets: list[FacetSchema] = Field(default_factory=list)

    def facet(self, slug: str) -> FacetSchema | None:
        return next((facet for facet in self.facets if facet.slug == slug), None)
