import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AttachmentClaim:
    job_id: uuid.UUID
    attempt_id: uuid.UUID
    generation: int
    attachment_id: uuid.UUID
