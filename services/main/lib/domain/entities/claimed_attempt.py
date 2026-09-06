import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClaimedAttempt:
    job_id: uuid.UUID
    attempt_id: uuid.UUID
    generation: int
