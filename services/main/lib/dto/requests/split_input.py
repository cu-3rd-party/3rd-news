import uuid

from pydantic import BaseModel, Field


class SplitInput(BaseModel):
    submission_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
