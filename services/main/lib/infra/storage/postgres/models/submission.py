from __future__ import annotations

import uuid
from datetime import datetime

from .common import (
    JSON_TYPE,
    Base,
    DateTime,
    ForeignKey,
    JsonObject,
    Mapped,
    String,
    UniqueConstraint,
    Uuid,
    func,
    mapped_column,
)
from .timestamp_mixin import TimestampMixin


class Submission(TimestampMixin, Base):
    __tablename__ = "submissions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str | None] = mapped_column(String(500))
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[JsonObject] = mapped_column(JSON_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="accepted", index=True)
    news_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("news.id", ondelete="SET NULL"), index=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_submission_source_external"),
        UniqueConstraint("idempotency_key", name="uq_submission_idempotency"),
    )
