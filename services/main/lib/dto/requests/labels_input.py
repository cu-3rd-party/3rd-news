from pydantic import BaseModel, Field


class LabelsInput(BaseModel):
    labels: dict[str, list[str]]
    release_facets: list[str] = Field(default_factory=list)
