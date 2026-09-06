from datetime import datetime
from typing import Annotated, Any

from pydantic import Field

from .classify_attachment import ClassifyAttachment
from .contract_model import ContractModel


class ClassifyNews(ContractModel):
    id: str
    version: Annotated[int, Field(ge=1)]
    title: str | None = None
    body_md: str
    source_link: str | None = None
    source_text: str | None = None
    published_at: datetime | None = None
    received_at: datetime | None = None
    lang: str | None = None
    attachments: list[ClassifyAttachment] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
