from __future__ import annotations

import uuid

from .common import (
    JSON_LIST,
    Base,
    Boolean,
    ForeignKey,
    Integer,
    Mapped,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    mapped_column,
)
from .timestamp_mixin import TimestampMixin


class FacetValue(TimestampMixin, Base):
    __tablename__ = "facet_values"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    facet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facets.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ai_hint: Mapped[str | None] = mapped_column(Text)
    synonyms: Mapped[list[str]] = mapped_column(JSON_LIST, default=list)
    match_patterns: Mapped[list[str]] = mapped_column(JSON_LIST, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("facet_id", "slug", name="uq_facet_value_slug"),)
