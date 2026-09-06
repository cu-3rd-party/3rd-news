from __future__ import annotations

import uuid
from datetime import datetime

from .common import (
    JSON_TYPE,
    Base,
    DateTime,
    ForeignKey,
    Integer,
    JsonObject,
    Mapped,
    String,
    Text,
    Uuid,
    func,
    mapped_column,
)
from .timestamp_mixin import TimestampMixin


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    news_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), index=True
    )
    classifier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("classifiers.id", ondelete="SET NULL")
    )
    current_attempt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    owner: Mapped[str | None] = mapped_column(String(512))
    payload: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    result: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
