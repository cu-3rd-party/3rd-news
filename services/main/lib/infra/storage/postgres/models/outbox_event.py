from __future__ import annotations

import uuid
from datetime import datetime

from .common import (
    JSON_TYPE,
    Base,
    DateTime,
    Integer,
    JsonObject,
    Mapped,
    String,
    Text,
    Uuid,
    func,
    mapped_column,
)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(String(120), index=True)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    payload: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    owner: Mapped[str | None] = mapped_column(String(512))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
