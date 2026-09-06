from pydantic import Field

from .contract_model import ContractModel


class ClassificationError(ContractModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
