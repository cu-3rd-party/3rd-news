from datetime import datetime
from typing import Any

from pydantic import Field, HttpUrl, model_validator

from ..domain.entities.text_validation import reject_unsafe_controls
from .attachment_input import AttachmentInput
from .contract_model import ContractModel


class NewsSubmission(ContractModel):
    source: str | None = Field(default=None, min_length=1, max_length=200)
    external_id: str | None = Field(default=None, min_length=1, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=500)
    title: str | None = Field(default=None, max_length=1000)
    body_md: str = Field(max_length=2_000_000)
    source_link: HttpUrl | None = Field(default=None, max_length=2083)
    source_text: str | None = Field(default=None, max_length=1000)
    published_at: datetime | None = None
    lang: str | None = Field(default=None, min_length=2, max_length=35)
    attachments: list[AttachmentInput] = Field(default_factory=list, max_length=100)
    extra: dict[str, Any] = Field(default_factory=dict)
    labels: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def stable_identity(self) -> NewsSubmission:
        source_identity = self.source is not None and self.external_id is not None
        if not source_identity and self.idempotency_key is None:
            raise ValueError("source + external_id or idempotency_key is required")
        if (self.source is None) != (self.external_id is None):
            raise ValueError("source and external_id must be supplied together")
        reject_unsafe_controls(self.model_dump(mode="python"))
        return self
