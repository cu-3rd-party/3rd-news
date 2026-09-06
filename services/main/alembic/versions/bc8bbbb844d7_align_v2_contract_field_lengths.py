from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "bc8bbbb844d7"
down_revision = "0cbddfef756e"
branch_labels = None
depends_on = None


def emit_squawk_file_directive() -> None:
    context = op.get_context()
    if context.as_sql:
        context.impl.static_output("-- squawk-ignore-file changing-column-type")


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    emit_squawk_file_directive()
    op.alter_column(
        "attachments",
        "original_url",
        existing_type=sa.VARCHAR(length=2000),
        type_=sa.String(length=2083),
        existing_nullable=True,
    )
    op.alter_column(
        "attachments",
        "filename",
        existing_type=sa.VARCHAR(length=500),
        type_=sa.String(length=1000),
        existing_nullable=True,
    )
    op.alter_column(
        "attachments",
        "content_type",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "audit_log",
        "actor",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=512),
        existing_nullable=False,
    )
    op.alter_column(
        "classifiers",
        "endpoint",
        existing_type=sa.VARCHAR(length=2000),
        type_=sa.String(length=2083),
        existing_nullable=False,
    )
    op.alter_column(
        "jobs",
        "owner",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=512),
        existing_nullable=True,
    )
    op.alter_column(
        "news_labels",
        "origin_key",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=512),
        existing_nullable=False,
    )
    op.alter_column(
        "news_versions",
        "source_link",
        existing_type=sa.VARCHAR(length=2000),
        type_=sa.String(length=2083),
        existing_nullable=True,
    )
    op.alter_column(
        "news_versions",
        "source_text",
        existing_type=sa.VARCHAR(length=500),
        type_=sa.String(length=1000),
        existing_nullable=True,
    )
    op.alter_column(
        "news_versions",
        "language",
        existing_type=sa.VARCHAR(length=32),
        type_=sa.String(length=35),
        existing_nullable=True,
    )
    op.alter_column(
        "news_versions",
        "created_by",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=512),
        existing_nullable=False,
    )
    op.alter_column(
        "outbox_events",
        "owner",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=512),
        existing_nullable=True,
    )
    op.alter_column(
        "sources",
        "url",
        existing_type=sa.VARCHAR(length=2000),
        type_=sa.String(length=2083),
        existing_nullable=True,
    )
    op.alter_column(
        "submissions",
        "idempotency_key",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=500),
        existing_nullable=True,
    )
    op.alter_column(
        "upload_intents",
        "owner_id",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=512),
        existing_nullable=False,
    )
    op.alter_column(
        "upload_intents",
        "content_type",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.alter_column(
        "upload_intents",
        "content_type",
        existing_type=sa.String(length=255),
        type_=sa.VARCHAR(length=200),
        existing_nullable=False,
    )
    op.alter_column(
        "upload_intents",
        "owner_id",
        existing_type=sa.String(length=512),
        type_=sa.VARCHAR(length=200),
        existing_nullable=False,
    )
    op.alter_column(
        "submissions",
        "idempotency_key",
        existing_type=sa.String(length=500),
        type_=sa.VARCHAR(length=200),
        existing_nullable=True,
    )
    op.alter_column(
        "sources",
        "url",
        existing_type=sa.String(length=2083),
        type_=sa.VARCHAR(length=2000),
        existing_nullable=True,
    )
    op.alter_column(
        "outbox_events",
        "owner",
        existing_type=sa.String(length=512),
        type_=sa.VARCHAR(length=200),
        existing_nullable=True,
    )
    op.alter_column(
        "news_versions",
        "created_by",
        existing_type=sa.String(length=512),
        type_=sa.VARCHAR(length=200),
        existing_nullable=False,
    )
    op.alter_column(
        "news_versions",
        "language",
        existing_type=sa.String(length=35),
        type_=sa.VARCHAR(length=32),
        existing_nullable=True,
    )
    op.alter_column(
        "news_versions",
        "source_text",
        existing_type=sa.String(length=1000),
        type_=sa.VARCHAR(length=500),
        existing_nullable=True,
    )
    op.alter_column(
        "news_versions",
        "source_link",
        existing_type=sa.String(length=2083),
        type_=sa.VARCHAR(length=2000),
        existing_nullable=True,
    )
    op.alter_column(
        "news_labels",
        "origin_key",
        existing_type=sa.String(length=512),
        type_=sa.VARCHAR(length=200),
        existing_nullable=False,
    )
    op.alter_column(
        "jobs",
        "owner",
        existing_type=sa.String(length=512),
        type_=sa.VARCHAR(length=200),
        existing_nullable=True,
    )
    op.alter_column(
        "classifiers",
        "endpoint",
        existing_type=sa.String(length=2083),
        type_=sa.VARCHAR(length=2000),
        existing_nullable=False,
    )
    op.alter_column(
        "audit_log",
        "actor",
        existing_type=sa.String(length=512),
        type_=sa.VARCHAR(length=200),
        existing_nullable=False,
    )
    op.alter_column(
        "attachments",
        "content_type",
        existing_type=sa.String(length=255),
        type_=sa.VARCHAR(length=200),
        existing_nullable=True,
    )
    op.alter_column(
        "attachments",
        "filename",
        existing_type=sa.String(length=1000),
        type_=sa.VARCHAR(length=500),
        existing_nullable=True,
    )
    op.alter_column(
        "attachments",
        "original_url",
        existing_type=sa.String(length=2083),
        type_=sa.VARCHAR(length=2000),
        existing_nullable=True,
    )
