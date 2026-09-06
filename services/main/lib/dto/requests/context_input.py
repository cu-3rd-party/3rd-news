from pydantic import BaseModel, Field


class ContextInput(BaseModel):
    text: str = Field(max_length=20_000)
    examples_enabled: bool | None = None
    examples_limit: int | None = Field(default=None, ge=1, le=50)
