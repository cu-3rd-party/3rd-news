from __future__ import annotations

from datetime import datetime

from .common import Base, CheckConstraint, DateTime, Integer, Mapped, String, mapped_column


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        CheckConstraint("scope IN ('account', 'ip')", name="auth_rate_limit_scope"),
        CheckConstraint("failure_count > 0", name="auth_rate_limit_failure_count"),
    )

    scope: Mapped[str] = mapped_column(String(16), primary_key=True)
    identifier_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
