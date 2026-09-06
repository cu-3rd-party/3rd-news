from __future__ import annotations

import uuid

from .common import (
    JSON_TYPE,
    Base,
    Boolean,
    Integer,
    JsonObject,
    Mapped,
    String,
    UniqueConstraint,
    Uuid,
    mapped_column,
)
from .timestamp_mixin import TimestampMixin


class EditorialRule(TimestampMixin, Base):
    __tablename__ = "editorial_rules"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    definition: Mapped[JsonObject] = mapped_column(JSON_TYPE, default=dict)
    __table_args__ = (UniqueConstraint("name", "version", name="uq_editorial_rule_version"),)
