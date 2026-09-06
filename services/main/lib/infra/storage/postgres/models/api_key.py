from __future__ import annotations

import uuid
from datetime import datetime

from .common import (
    JSON_LIST,
    JSON_OBJECT,
    Base,
    Boolean,
    DateTime,
    ForeignKey,
    JsonObject,
    Mapped,
    String,
    Uuid,
    mapped_column,
)
from .timestamp_mixin import TimestampMixin


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    prefix: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON_LIST, default=list)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    filter_preset: Mapped[JsonObject] = mapped_column(JSON_OBJECT, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
