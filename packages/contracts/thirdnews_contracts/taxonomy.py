"""Classification taxonomy.

The taxonomy is *data*, not code: admins create facets (axes) and their values
at runtime. A classifier never hardcodes facet slugs — it receives the whole
taxonomy in every request and answers only for the facets it understands.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FacetType(str, Enum):
    """How many values of one facet a single news item may carry."""

    SINGLE = "single"
    MULTI = "multi"


class FacetValueSchema(BaseModel):
    slug: str
    title: str
    description: str | None = None
    #: Free-form hint shown to an LLM classifier ("выбирай, если ...").
    ai_hint: str | None = None
    #: Plain keywords, matched case-insensitively on word boundaries.
    synonyms: list[str] = Field(default_factory=list)
    #: Python-flavoured regular expressions, matched case-insensitively.
    match_patterns: list[str] = Field(default_factory=list)
    position: int = 0


class FacetSchema(BaseModel):
    slug: str
    title: str
    description: str | None = None
    ai_hint: str | None = None
    type: FacetType = FacetType.SINGLE
    #: A required facet blocks publication until it gets a value.
    required: bool = False
    position: int = 0
    values: list[FacetValueSchema] = Field(default_factory=list)


class Taxonomy(BaseModel):
    version: str = "1.0"
    facets: list[FacetSchema] = Field(default_factory=list)

    def facet(self, slug: str) -> FacetSchema | None:
        return next((f for f in self.facets if f.slug == slug), None)
