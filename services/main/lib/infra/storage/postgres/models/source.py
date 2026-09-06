from __future__ import annotations

import uuid
from datetime import datetime

from .common import (
    JSON_OBJECT,
    Base,
    Boolean,
    DateTime,
    JsonObject,
    Mapped,
    String,
    Text,
    Uuid,
    mapped_column,
)
from .timestamp_mixin import TimestampMixin


class Source(TimestampMixin, Base):
    __tablename__ = "sources"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), default="other", nullable=False)
    url: Mapped[str | None] = mapped_column(String(2083))
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    skip_classification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_labels: Mapped[JsonObject] = mapped_column(JSON_OBJECT, default=dict)
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
