from datetime import datetime

from pydantic import HttpUrl

from .contract_model import ContractModel


class CallbackSpec(ContractModel):
    url: HttpUrl
    deadline_at: datetime
    audience: str
