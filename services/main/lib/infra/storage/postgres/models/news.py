from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .news_version import NewsVersion

from .common import (
    JSON_LIST,
    Base,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Mapped,
    String,
    Uuid,
    mapped_column,
    relationship,
)
from .timestamp_mixin import TimestampMixin


class News(TimestampMixin, Base):
    __tablename__ = "news"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "news_versions.id", use_alter=True, ondelete="RESTRICT", name="fk_news_current_version"
        ),
        nullable=True,
    )
    current_attempt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    revision: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    visibility_revision: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    urgency: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    editorial_priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_facets: Mapped[list[str]] = mapped_column(JSON_LIST, default=list)
    is_gold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_version: Mapped[NewsVersion | None] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )
    versions: Mapped[list[NewsVersion]] = relationship(
        back_populates="news", foreign_keys="NewsVersion.news_id", cascade="all, delete-orphan"
    )
    __table_args__ = (
        CheckConstraint("urgency between 0 and 100", name="urgency_range"),
        CheckConstraint("impact between 0 and 100", name="impact_range"),
        CheckConstraint("editorial_priority between 0 and 100", name="editorial_priority_range"),
        CheckConstraint(
            "importance = urgency + impact + editorial_priority", name="importance_sum"
        ),
    )
