from __future__ import annotations

import uuid
from datetime import datetime

from .common import Base, BigInteger, DateTime, ForeignKey, Mapped, String, Uuid, mapped_column
from .timestamp_mixin import TimestampMixin


class UploadIntent(TimestampMixin, Base):
    __tablename__ = "upload_intents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(String(512), index=True)
    temp_key: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    final_key: Mapped[str | None] = mapped_column(String(1000), unique=True)
    expected_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attachments.id", ondelete="SET NULL")
    )
