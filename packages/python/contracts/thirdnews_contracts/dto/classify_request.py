from typing import Literal

from pydantic import Field, model_validator

from .classify_news import ClassifyNews
from .classify_options import ClassifyOptions
from .contract_model import ContractModel
from .labeled_example import LabeledExample
from .taxonomy import Taxonomy


class ClassifyRequest(ContractModel):
    contract_version: Literal["2.0"] = "2.0"
    request_id: str
    job_id: str
    attempt_id: str
    news: ClassifyNews
    taxonomy: Taxonomy
    options: ClassifyOptions = Field(default_factory=ClassifyOptions)
    context: str | None = None
    examples: list[LabeledExample] = Field(default_factory=list)

    @model_validator(mode="after")
    def allowed_axes_exist(self) -> ClassifyRequest:
        known = {axis.slug for axis in self.taxonomy.facets}
        unknown = set(self.options.allowed_axes) - known
        if unknown:
            raise ValueError(f"unknown allowed axes: {sorted(unknown)}")
        return self
