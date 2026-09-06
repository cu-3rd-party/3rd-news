from __future__ import annotations

import uuid
from datetime import datetime

from .common import (
    JSON_LIST,
    JSON_TYPE,
    Base,
    Boolean,
    DateTime,
    Float,
    Integer,
    JsonObject,
    Mapped,
    String,
    Text,
    Uuid,
    mapped_column,
)
from .timestamp_mixin import TimestampMixin


class Classifier(TimestampMixin, Base):
    __tablename__ = "classifiers"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(2083), nullable=False)
    allowed_axes: Mapped[list[str]] = mapped_column(JSON_LIST, default=list)
    config: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    signing_public_key: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    shadow: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=30.0)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
