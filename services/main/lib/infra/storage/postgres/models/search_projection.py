from __future__ import annotations

import uuid

from .common import Base, BigInteger, ForeignKey, Mapped, String, Text, mapped_column
from .timestamp_mixin import TimestampMixin


class SearchProjection(TimestampMixin, Base):
    __tablename__ = "search_projections"
    news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), primary_key=True
    )
    desired_revision: Mapped[int] = mapped_column(BigInteger, default=0)
    indexed_revision: Mapped[int] = mapped_column(BigInteger, default=0)
    visibility_revision: Mapped[int] = mapped_column(BigInteger, default=0)
    task_uid: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
