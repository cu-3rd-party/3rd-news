from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .news import News

from .common import (
    JSON_TYPE,
    Base,
    DateTime,
    ForeignKey,
    Integer,
    JsonObject,
    Mapped,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    mapped_column,
    relationship,
)


class NewsVersion(Base):
    __tablename__ = "news_versions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000))
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    source_link: Mapped[str | None] = mapped_column(String(2083))
    source_text: Mapped[str | None] = mapped_column(String(1000))
    language: Mapped[str | None] = mapped_column(String(35))
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    created_by: Mapped[str] = mapped_column(String(512), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    news: Mapped[News] = relationship(back_populates="versions", foreign_keys=[news_id])
    __table_args__ = (UniqueConstraint("news_id", "number", name="uq_news_version_number"),)
