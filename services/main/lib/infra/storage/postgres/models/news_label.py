from __future__ import annotations

import uuid
from datetime import datetime

from .common import (
    JSON_TYPE,
    Base,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    JsonObject,
    Mapped,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    mapped_column,
)


class NewsLabel(Base):
    __tablename__ = "news_labels"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news_versions.id", ondelete="CASCADE"), index=True
    )
    facet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facets.id", ondelete="CASCADE"), index=True
    )
    value_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facet_values.id", ondelete="CASCADE"), index=True
    )
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    origin_key: Mapped[str] = mapped_column(String(512), default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    reason: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint(
            "news_id",
            "version_id",
            "value_id",
            "origin",
            "origin_key",
            name="uq_news_label_opinion",
        ),
        CheckConstraint("confidence between 0 and 1", name="confidence_range"),
    )
