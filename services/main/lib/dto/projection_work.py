import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProjectionWork:
    news_id: uuid.UUID
    revision: int
    visibility_revision: int
    existing_task_uid: int | None
