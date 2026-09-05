"""Database schema.

Design note: the classification taxonomy is stored as rows (`facets` /
`facet_values`), never as enums in code, so an admin can add a new axis
("для потока 2027") without a migration or a redeploy.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from .db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --------------------------------------------------------------------------- #
# Identity and access
# --------------------------------------------------------------------------- #


class User(TimestampMixin, Base):
    """An admin-panel operator. End readers do not need a user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(512))
    #: "admin" (everything) or "editor" (news and labels, no keys/users).
    role: Mapped[str] = mapped_column(String(32), default="editor", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Set for accounts created by an external identity provider.
    sso_subject: Mapped[str | None] = mapped_column(String(320), unique=True)
    sso_provider: Mapped[str | None] = mapped_column(String(64))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete")


class Session(Base):
    """Cookie session for the admin SPA and for cookie-authenticated readers."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class Source(TimestampMixin, Base):
    """A channel news comes from, and implicitly the parser that reads it."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    #: "telegram", "vk", "rss", "site", "manual", ...
    kind: Mapped[str] = mapped_column(String(64), default="other", nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Labels applied to everything from this source (e.g. a fixed faculty),
    #: shaped as {"facet-slug": ["value-slug", ...]}.
    default_labels: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    #: Skip the classification pipeline for this source.
    skip_classification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_ingest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="source")


class ApiKey(TimestampMixin, Base):
    """Issued in the admin. Used by parsers (ingest) and by readers (read)."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: First characters of the key, kept so a human can recognise it in lists.
    prefix: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    #: Subset of {"ingest", "read", "admin"}.
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list, nullable=False)
    #: Parser keys are bound to a source; its slug becomes the default source_key.
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    #: Reader keys may be limited to a slice of the archive; same shape as the
    #: query parameters of the delivery endpoint.
    filter_preset: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[Source | None] = relationship(back_populates="api_keys")


# --------------------------------------------------------------------------- #
# Taxonomy
# --------------------------------------------------------------------------- #


class Facet(TimestampMixin, Base):
    """One independent axis of classification (importance, stream, kind, ...)."""

    __tablename__ = "facets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ai_hint: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(16), default="single", nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    values: Mapped[list["FacetValue"]] = relationship(
        back_populates="facet", cascade="all, delete-orphan", order_by="FacetValue.position"
    )

    __table_args__ = (CheckConstraint("type in ('single','multi')", name="ck_facets_type"),)


class FacetValue(TimestampMixin, Base):
    __tablename__ = "facet_values"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    facet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ai_hint: Mapped[str | None] = mapped_column(Text)
    #: Keyword and regex rules; consumed by the regex classifier as-is.
    synonyms: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    match_patterns: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    facet: Mapped[Facet] = relationship(back_populates="values")

    __table_args__ = (UniqueConstraint("facet_id", "slug", name="uq_facet_values_facet_slug"),)


# --------------------------------------------------------------------------- #
# News
# --------------------------------------------------------------------------- #


class News(TimestampMixin, Base):
    __tablename__ = "news"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(400))
    title: Mapped[str | None] = mapped_column(String(1000))
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    source_link: Mapped[str | None] = mapped_column(String(2000))
    source_text: Mapped[str | None] = mapped_column(String(500))
    lang: Mapped[str | None] = mapped_column(String(16))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    #: When the item reached this service. Never null, never from the parser.
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    #: pending -> classified -> published, plus rejected / needs_review.
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    #: sha256 of the normalised body, for cross-source duplicate detection.
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ingested_by_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL")
    )
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    #: Set once every enabled classifier has answered (or given up).
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Facets an editor has taken over. Listing a facet here freezes it against
    #: classifiers — including the case "the editor decided it has no value",
    #: which is otherwise indistinguishable from "nobody labelled it yet".
    manual_facets: Mapped[list[str]] = mapped_column(
        ARRAY(String(120)), default=list, nullable=False
    )
    #: Золотая новость — эталон для измерения качества классификаторов.
    #: Размечена руками, но никогда не отдаётся классификаторам как пример,
    #: иначе тест утёк бы в подсказку. См. knowledge.collect_examples.
    is_gold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    source: Mapped[Source | None] = relationship()
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="news", cascade="all, delete-orphan", order_by="Attachment.position"
    )
    labels: Mapped[list["NewsLabel"]] = relationship(
        back_populates="news", cascade="all, delete-orphan"
    )
    effective_labels: Mapped[list["NewsEffectiveLabel"]] = relationship(
        back_populates="news", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_news_source_external"),
    )


class Attachment(TimestampMixin, Base):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), default="file", nullable=False)
    #: Where it came from; kept even after a successful download.
    original_url: Mapped[str | None] = mapped_column(String(2000))
    #: Path relative to `settings.media_root`. Null until downloaded.
    storage_path: Mapped[str | None] = mapped_column(String(1000))
    filename: Mapped[str | None] = mapped_column(String(500))
    mime: Mapped[str | None] = mapped_column(String(200))
    size: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(64))
    caption: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: pending -> stored | failed
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    news: Mapped[News] = relationship(back_populates="attachments")


class NewsLabel(Base):
    """Every opinion about a news item, including disagreeing ones.

    Nothing is overwritten: a manual edit and three classifiers all leave their
    own rows here, and `news_effective_labels` holds the resolved answer.
    """

    __tablename__ = "news_labels"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facet_values.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: "manual" | "classifier" | "parser" | "source_default"
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Identifies the specific opinion holder: classifier slug, user id, ...
    origin_key: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    news: Mapped[News] = relationship(back_populates="labels")
    facet: Mapped[Facet] = relationship()
    value: Mapped[FacetValue] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "news_id", "value_id", "origin", "origin_key", name="uq_news_labels_opinion"
        ),
    )


class NewsEffectiveLabel(Base):
    """Resolved labels — the only thing the delivery endpoint filters on."""

    __tablename__ = "news_effective_labels"

    news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), primary_key=True
    )
    value_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facet_values.id", ondelete="CASCADE"), primary_key=True
    )
    facet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    news: Mapped[News] = relationship(back_populates="effective_labels")
    facet: Mapped[Facet] = relationship()
    value: Mapped[FacetValue] = relationship()

    __table_args__ = (Index("ix_effective_facet_value", "facet_id", "value_id"),)


# --------------------------------------------------------------------------- #
# Classification services
# --------------------------------------------------------------------------- #


class Classifier(TimestampMixin, Base):
    """A registered classification microservice, wherever it happens to live."""

    __tablename__ = "classifiers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    base_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    #: Shared HMAC secret; also accepted on the async callback.
    secret: Mapped[str | None] = mapped_column(String(512))
    #: Facet slugs to ask this service about; empty means "all of them".
    facets: Mapped[list[str]] = mapped_column(ARRAY(String(120)), default=list, nullable=False)
    #: Passed through to the service as `options.config`.
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Higher priority wins when two classifiers disagree on the same facet.
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    #: False = proposals are stored for review but never become effective.
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timeout_s: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClassificationJob(TimestampMixin, Base):
    __tablename__ = "classification_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    news_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), nullable=False, index=True
    )
    classifier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classifiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: queued -> running -> (awaiting_callback) -> done | failed
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    news: Mapped[News] = relationship()
    classifier: Mapped[Classifier] = relationship()

    __table_args__ = (UniqueConstraint("news_id", "classifier_id", name="uq_job_news_classifier"),)


class Setting(Base):
    """Настройки, которые редактор меняет в админке, а не в .env.

    Пока здесь живёт один ключ — текст про организацию для классификаторов.
    Таблица, а не конфиг, именно потому, что это редакторские данные: их
    правят на ходу и без перезапуска.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(120))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
