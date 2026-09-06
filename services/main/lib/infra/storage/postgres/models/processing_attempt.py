from __future__ import annotations

import uuid
from datetime import datetime

from .common import (
    JSON_TYPE,
    Base,
    DateTime,
    ForeignKey,
    Integer,
    JsonObject,
    LargeBinary,
    Mapped,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    mapped_column,
)


class ProcessingAttempt(Base):
    __tablename__ = "processing_attempts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    news_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("news_versions.id", ondelete="CASCADE")
    )
    classifier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("classifiers.id", ondelete="SET NULL")
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running")
    callback_token_hash: Mapped[str | None] = mapped_column(String(128), unique=True)
    callback_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_payload: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    raw_request_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    raw_payload_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    validated_result: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    evidence: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    model: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    taxonomy_version: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    schema_version: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("job_id", "generation", name="uq_attempt_job_generation"),)
