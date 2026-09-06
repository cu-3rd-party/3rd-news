from pydantic import BaseModel, Field


class SelectIn(BaseModel):
    channels: list[str] = Field(min_length=1)
