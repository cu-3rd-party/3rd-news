import uuid

from pydantic import BaseModel, Field


class GoldInput(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    is_gold: bool = True
