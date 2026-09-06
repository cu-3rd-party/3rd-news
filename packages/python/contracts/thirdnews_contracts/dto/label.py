from pydantic import BaseModel


class Label(BaseModel):
    facet: str
    facet_title: str | None = None
    value: str
    value_title: str | None = None
    origin: str = "manual"
    confidence: float | None = None
