from __future__ import annotations

import uuid
from datetime import datetime

from .common import (
    Base,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Mapped,
    String,
    func,
    mapped_column,
)


class SimilarityCandidate(Base):
    __tablename__ = "similarity_candidates"
    left_news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), primary_key=True
    )
    right_news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("left_news_id <> right_news_id", name="distinct_news"),)
