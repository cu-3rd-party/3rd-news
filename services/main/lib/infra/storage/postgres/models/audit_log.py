from __future__ import annotations

import uuid
from datetime import datetime

from .common import JSON_TYPE, Base, DateTime, JsonObject, Mapped, String, Uuid, func, mapped_column


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(512), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(120))
    payload: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
