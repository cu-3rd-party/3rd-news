from typing import Annotated

from pydantic import Field, HttpUrl, model_validator

from ..domain.entities.text_validation import reject_unsafe_controls
from .attachment_kind import AttachmentKind
from .contract_model import ContractModel


class AttachmentInput(ContractModel):
    kind: AttachmentKind = AttachmentKind.FILE
    url: Annotated[HttpUrl, Field(max_length=2083)] | None = None
    upload_intent_id: str | None = None
    filename: str | None = Field(default=None, max_length=1000)
    mime: str | None = Field(default=None, max_length=255)
    caption: str | None = None
    position: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def one_source(self) -> AttachmentInput:
        if (self.url is None) == (self.upload_intent_id is None):
            raise ValueError("attachment requires exactly one of url or upload_intent_id")
        reject_unsafe_controls(self.model_dump(mode="python"), "attachment")
        return self
