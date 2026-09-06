from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .facet_value import FacetValue

from .common import (
    Base,
    Boolean,
    CheckConstraint,
    Integer,
    Mapped,
    String,
    Text,
    Uuid,
    mapped_column,
    relationship,
)
from .timestamp_mixin import TimestampMixin


class Facet(TimestampMixin, Base):
    __tablename__ = "facets"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ai_hint: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="single")
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    values: Mapped[list[FacetValue]] = relationship(
        cascade="all, delete-orphan", order_by="FacetValue.position"
    )
    __table_args__ = (CheckConstraint("kind in ('single','multi')", name="facet_kind"),)
