from __future__ import annotations

import uuid

from .common import (
    Base,
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Mapped,
    String,
    Text,
    Uuid,
    mapped_column,
)
from .timestamp_mixin import TimestampMixin


class Attachment(TimestampMixin, Base):
    __tablename__ = "attachments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL"), index=True
    )
    news_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), index=True
    )
    object_key: Mapped[str | None] = mapped_column(String(1000), unique=True)
    original_url: Mapped[str | None] = mapped_column(String(2083))
    filename: Mapped[str | None] = mapped_column(String(1000))
    content_type: Mapped[str | None] = mapped_column(String(255))
    size: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32), default="file")
    caption: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
