import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AcceptedSubmission:
    submission_id: uuid.UUID
    status: str
    received_at: datetime
