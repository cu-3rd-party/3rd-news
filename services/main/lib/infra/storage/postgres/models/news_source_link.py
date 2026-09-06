from __future__ import annotations

import uuid

from .common import Base, ForeignKey, Mapped, String, mapped_column


class NewsSourceLink(Base):
    __tablename__ = "news_source_links"
    news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), primary_key=True
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="RESTRICT"), primary_key=True
    )
    relation: Mapped[str] = mapped_column(String(32), default="origin")
