from typing import Literal

from pydantic import Field

from .contract_model import ContractModel


class ClassifierManifest(ContractModel):
    slug: str
    name: str
    version: str
    contract_version: Literal["2.0"] = "2.0"
    axes: list[str] = Field(default_factory=lambda: ["*"])
    supports_async: bool = False
    description: str | None = None
