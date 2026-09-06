from pydantic import Field

from .contract_model import ContractModel


class EventMetadata(ContractModel):
    correlation_id: str
    causation_id: str | None = None
    actor_id: str | None = None
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
