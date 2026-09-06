from pydantic import Field

from .contract_model import ContractModel


class CompletedUpload(ContractModel):
    upload_id: str
    status: str = Field(pattern="^completed$")
    object_key: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
