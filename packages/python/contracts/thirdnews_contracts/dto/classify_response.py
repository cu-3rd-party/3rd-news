from typing import Any, Literal

from pydantic import Field, model_validator

from .ai_trace import AITrace
from .classification_error import ClassificationError
from .classification_status import ClassificationStatus
from .contract_model import ContractModel
from .proposed_label import ProposedLabel


class ClassifyResponse(ContractModel):
    contract_version: Literal["2.0"] = "2.0"
    request_id: str
    job_id: str
    attempt_id: str
    news_id: str
    news_version: int = Field(ge=1)
    classifier: str
    node_id: str
    status: ClassificationStatus
    error: ClassificationError | None = None
    labels: list[ProposedLabel] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    trace: AITrace | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_outcome(self) -> ClassifyResponse:
        if self.status is ClassificationStatus.FAILED:
            if self.error is None:
                raise ValueError("failed classification requires error")
            if self.labels:
                raise ValueError("failed classification cannot contain labels")
        elif self.error is not None:
            raise ValueError("completed classification cannot contain error")
        return self
