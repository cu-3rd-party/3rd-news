from pydantic import Field, model_validator

from ..domain.entities.text_validation import reject_unsafe_controls
from .contract_model import ContractModel


class UploadIntentRequest(ContractModel):
    filename: str = Field(min_length=1, max_length=1000)
    content_type: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def safe_text(self) -> UploadIntentRequest:
        reject_unsafe_controls(self.model_dump(mode="python"), "upload")
        return self
