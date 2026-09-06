from __future__ import annotations

import uuid

from .common import Base, Float, ForeignKey, Mapped, String, mapped_column


class NewsEffectiveLabel(Base):
    __tablename__ = "news_effective_labels"
    news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), primary_key=True
    )
    facet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facets.id", ondelete="CASCADE"), primary_key=True
    )
    value_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facet_values.id", ondelete="CASCADE"), primary_key=True
    )
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
