from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index

from .common import (
    JSON_TYPE,
    Base,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    JsonObject,
    Mapped,
    String,
    UniqueConstraint,
    Uuid,
    func,
    mapped_column,
)


class ManualLabelDecision(Base):
    __tablename__ = "manual_label_decisions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news_versions.id", ondelete="CASCADE"), index=True
    )
    facet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facets.id", ondelete="RESTRICT"), index=True
    )
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "news_id",
            "version_id",
            "facet_id",
            "revision",
            name="uq_manual_decision_revision",
        ),
        CheckConstraint("action in ('set','release')", name="manual_decision_action"),
        CheckConstraint("origin in ('manual','provenance')", name="manual_decision_origin"),
        Index(
            "ix_manual_decision_latest",
            "news_id",
            "version_id",
            "facet_id",
            "revision",
        ),
    )
