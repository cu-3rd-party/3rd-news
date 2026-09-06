from __future__ import annotations

from datetime import datetime

from .common import JSON_TYPE, Base, DateTime, JsonObject, Mapped, String, func, mapped_column


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
