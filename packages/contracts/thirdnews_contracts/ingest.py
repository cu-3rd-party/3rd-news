"""What a parser sends to the main service (`POST /api/v1/ingest/news`)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl, model_validator


class AttachmentKind(str, Enum):
    IMAGE = "image"
    PDF = "pdf"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"


class AttachmentInput(BaseModel):
    """One attachment.

    Either `url` (the main service downloads it itself, asynchronously) or
    `upload_name` (the file is sent in the same multipart request under that
    form field name).
    """

    kind: AttachmentKind = AttachmentKind.FILE
    url: HttpUrl | None = None
    upload_name: str | None = None
    filename: str | None = None
    mime: str | None = None
    caption: str | None = None
    position: int = 0

    @model_validator(mode="after")
    def _one_source(self) -> "AttachmentInput":
        if bool(self.url) == bool(self.upload_name):
            raise ValueError("attachment needs exactly one of `url` or `upload_name`")
        return self


class NewsSubmission(BaseModel):
    """A single news item as produced by a parser."""

    #: Stable id of the item inside its source (message id, guid, ...).
    #: Together with `source_key` it makes ingestion idempotent.
    external_id: str | None = None
    #: Slug of the source registered in the admin ("tg-university-main").
    #: Defaults to the source bound to the API key.
    source_key: str | None = None

    title: str | None = None
    #: The body, Markdown. May be long; the service does not truncate it.
    body_md: str
    #: Link to the original post, when there is one.
    source_link: HttpUrl | None = None
    #: Human name of the channel when there is no link ("Деканат ФКН, Telegram").
    source_text: str | None = None
    #: When the news was published at the source.
    published_at: datetime | None = None
    lang: str | None = None
    attachments: list[AttachmentInput] = Field(default_factory=list)
    #: Anything the parser wants to keep; opaque to the platform.
    extra: dict = Field(default_factory=dict)
    #: Labels the parser is already sure about, as `{"facet": ["value", ...]}`.
    #: Stored with origin `parser` and overridden by manual edits.
    labels: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _has_attribution(self) -> "NewsSubmission":
        if not self.source_link and not self.source_text and not self.source_key:
            raise ValueError("one of `source_link`, `source_text` or `source_key` is required")
        return self


class IngestStatus(str, Enum):
    CREATED = "created"
    #: Same `source_key` + `external_id` was already ingested; nothing changed.
    DUPLICATE = "duplicate"


class IngestResult(BaseModel):
    id: str
    status: IngestStatus
    received_at: datetime
