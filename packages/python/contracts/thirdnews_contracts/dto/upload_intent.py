from datetime import datetime

from pydantic import Field, HttpUrl

from .contract_model import ContractModel


class UploadIntent(ContractModel):
    upload_id: str
    url: HttpUrl = Field(max_length=2083)
    method: str = Field(pattern="^PUT$")
    headers: dict[str, str]
    expires_at: datetime
