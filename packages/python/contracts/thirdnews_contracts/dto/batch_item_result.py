from datetime import datetime

from pydantic import Field

from .contract_model import ContractModel
from .ingest_status import IngestStatus


class BatchItemResult(ContractModel):
    index: int = Field(ge=0)
    status: IngestStatus
    submission_id: str | None = None
    received_at: datetime | None = None
    error: str | None = None
