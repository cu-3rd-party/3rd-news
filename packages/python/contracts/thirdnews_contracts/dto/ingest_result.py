from datetime import datetime

from .contract_model import ContractModel
from .ingest_status import IngestStatus


class IngestResult(ContractModel):
    submission_id: str
    status: IngestStatus
    received_at: datetime
