from pydantic import BaseModel


class Attachment(BaseModel):
    id: str
    kind: str
    url: str | None = None
    filename: str | None = None
    mime: str | None = None
    size: int | None = None
    caption: str | None = None
    position: int = 0
