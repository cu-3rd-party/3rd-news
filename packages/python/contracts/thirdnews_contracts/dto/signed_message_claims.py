from pydantic import Field

from .contract_model import ContractModel


class SignedMessageClaims(ContractModel):
    issuer: str
    audience: str
    issued_at: int
    expires_at: int
    token_id: str
    job_id: str
    attempt_id: str
    node_id: str
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
