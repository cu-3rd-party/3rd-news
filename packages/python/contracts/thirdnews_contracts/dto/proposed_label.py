from typing import Annotated

from pydantic import Field

from .contract_model import ContractModel
from .evidence import Evidence


class ProposedLabel(ContractModel):
    axis: str
    value: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    reason: str | None = Field(default=None, max_length=1000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)
