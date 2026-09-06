from typing import Literal

from pydantic import Field

from .contract_model import ContractModel


class LabeledExample(ContractModel):
    id: str | None = None
    title: str | None = None
    body_md: str
    labels: dict[str, list[str]] = Field(default_factory=dict)
    is_gold: Literal[False] = False
