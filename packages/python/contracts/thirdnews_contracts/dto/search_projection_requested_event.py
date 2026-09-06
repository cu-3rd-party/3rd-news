from datetime import datetime
from typing import Literal

from pydantic import Field

from .contract_model import ContractModel
from .event_metadata import EventMetadata


class SearchProjectionRequestedEvent(ContractModel):
    contract_version: Literal["2.0"] = "2.0"
    event_id: str
    event_type: Literal["search.projection.requested.v2"] = "search.projection.requested.v2"
    occurred_at: datetime
    aggregate_id: str
    aggregate_version: int
    metadata: EventMetadata
    payload: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
