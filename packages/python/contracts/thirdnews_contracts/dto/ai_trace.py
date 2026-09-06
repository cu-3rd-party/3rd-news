from typing import Annotated, Any

from pydantic import Field

from .contract_model import ContractModel


class AITrace(ContractModel):
    provider: str
    model: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str
    schema_version: str
    taxonomy_version: str
    request_payload: dict[str, Any]
    raw_response: dict[str, Any] | str | None = None
    duration_ms: Annotated[int, Field(ge=0)]
    error: str | None = None
