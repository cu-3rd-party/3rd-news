from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contract_model import ContractModel


class Evidence(ContractModel):
    kind: Literal["text", "attachment", "rule", "model"]
    excerpt: str | None = Field(default=None, max_length=1000)
    attachment_id: str | None = None
    start: Annotated[int, Field(ge=0)] | None = None
    end: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def valid_span(self) -> Evidence:
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("evidence end precedes start")
        return self
