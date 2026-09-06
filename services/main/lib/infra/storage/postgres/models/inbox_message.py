from __future__ import annotations

from datetime import datetime

from .common import Base, DateTime, Mapped, String, func, mapped_column


class InboxMessage(Base):
    __tablename__ = "inbox_messages"
    consumer_name: Mapped[str] = mapped_column(String(120), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
