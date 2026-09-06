from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0cbddfef756e"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_created_at"), "audit_log", ["created_at"], unique=False)
    op.create_index(op.f("ix_audit_log_request_id"), "audit_log", ["request_id"], unique=False)
    op.create_table(
        "classifiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("endpoint", sa.String(length=2000), nullable=False),
        sa.Column(
            "allowed_axes",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "config",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("signing_public_key", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("shadow", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("min_confidence", sa.Float(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classifiers")),
        sa.UniqueConstraint("slug", name=op.f("uq_classifiers_slug")),
    )
    op.create_table(
        "editorial_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "definition",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_editorial_rules")),
        sa.UniqueConstraint("name", "version", name="uq_editorial_rule_version"),
    )
    op.create_table(
        "facets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ai_hint", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind in ('single','multi')", name=op.f("ck_facets_facet_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_facets")),
        sa.UniqueConstraint("slug", name=op.f("uq_facets_slug")),
    )
    op.create_table(
        "inbox_messages",
        sa.Column("consumer_name", sa.String(length=120), nullable=False),
        sa.Column("message_id", sa.String(length=200), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("consumer_name", "message_id", name=op.f("pk_inbox_messages")),
    )
    op.create_table(
        "news",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("current_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("visibility_revision", sa.BigInteger(), nullable=False),
        sa.Column("urgency", sa.Integer(), nullable=False),
        sa.Column("impact", sa.Integer(), nullable=False),
        sa.Column("editorial_priority", sa.Integer(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column(
            "manual_facets",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("is_gold", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "editorial_priority between 0 and 100", name=op.f("ck_news_editorial_priority_range")
        ),
        sa.CheckConstraint("impact between 0 and 100", name=op.f("ck_news_impact_range")),
        sa.CheckConstraint(
            "importance = urgency + impact + editorial_priority",
            name=op.f("ck_news_importance_sum"),
        ),
        sa.CheckConstraint("urgency between 0 and 100", name=op.f("ck_news_urgency_range")),
        sa.ForeignKeyConstraint(
            ["current_version_id"],
            ["news_versions.id"],
            name="fk_news_current_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news")),
    )
    op.create_index(op.f("ix_news_published_at"), "news", ["published_at"], unique=False)
    op.create_index(op.f("ix_news_status"), "news", ["status"], unique=False)
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner", sa.String(length=200), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
    )
    op.create_index(
        "ix_outbox_claim",
        "outbox_events",
        ["delivered_at", "available_at", "lease_until"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_events_aggregate_id"), "outbox_events", ["aggregate_id"], unique=False
    )
    op.create_index(
        op.f("ix_outbox_events_available_at"), "outbox_events", ["available_at"], unique=False
    )
    op.create_index(
        op.f("ix_outbox_events_delivered_at"), "outbox_events", ["delivered_at"], unique=False
    )
    op.create_index(
        op.f("ix_outbox_events_lease_until"), "outbox_events", ["lease_until"], unique=False
    )
    op.create_index(op.f("ix_outbox_events_topic"), "outbox_events", ["topic"], unique=False)
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column(
            "value",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("skip_classification", sa.Boolean(), nullable=False),
        sa.Column(
            "default_labels",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
        sa.UniqueConstraint("slug", name=op.f("uq_sources_slug")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("password_hash", sa.String(length=512), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "scopes",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column(
            "filter_preset",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_api_keys_source_id_sources"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
        sa.UniqueConstraint("prefix", name=op.f("uq_api_keys_prefix")),
    )
    op.create_table(
        "facet_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("facet_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ai_hint", sa.Text(), nullable=True),
        sa.Column(
            "synonyms",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "match_patterns",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["facet_id"],
            ["facets.id"],
            name=op.f("fk_facet_values_facet_id_facets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_facet_values")),
        sa.UniqueConstraint("facet_id", "slug", name="uq_facet_value_slug"),
    )
    op.create_index(op.f("ix_facet_values_facet_id"), "facet_values", ["facet_id"], unique=False)
    op.create_table(
        "news_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("news_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=True),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("source_link", sa.String(length=2000), nullable=True),
        sa.Column("source_text", sa.String(length=500), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "extra",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["news_id"], ["news.id"], name=op.f("fk_news_versions_news_id_news"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news_versions")),
        sa.UniqueConstraint("news_id", "number", name="uq_news_version_number"),
    )
    op.create_index(op.f("ix_news_versions_news_id"), "news_versions", ["news_id"], unique=False)
    op.create_foreign_key(
        "fk_news_current_version",
        "news",
        "news_versions",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "search_projections",
        sa.Column("news_id", sa.Uuid(), nullable=False),
        sa.Column("desired_revision", sa.BigInteger(), nullable=False),
        sa.Column("indexed_revision", sa.BigInteger(), nullable=False),
        sa.Column("visibility_revision", sa.BigInteger(), nullable=False),
        sa.Column("task_uid", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["news_id"],
            ["news.id"],
            name=op.f("fk_search_projections_news_id_news"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("news_id", name=op.f("pk_search_projections")),
    )
    op.create_index(
        op.f("ix_search_projections_status"), "search_projections", ["status"], unique=False
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("csrf_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "similarity_candidates",
        sa.Column("left_news_id", sa.Uuid(), nullable=False),
        sa.Column("right_news_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "left_news_id <> right_news_id", name=op.f("ck_similarity_candidates_distinct_news")
        ),
        sa.ForeignKeyConstraint(
            ["left_news_id"],
            ["news.id"],
            name=op.f("fk_similarity_candidates_left_news_id_news"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["right_news_id"],
            ["news.id"],
            name=op.f("fk_similarity_candidates_right_news_id_news"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "left_news_id", "right_news_id", name=op.f("pk_similarity_candidates")
        ),
    )
    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.String(length=500), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "raw_payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("news_id", sa.Uuid(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["news_id"], ["news.id"], name=op.f("fk_submissions_news_id_news"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_submissions_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
        sa.UniqueConstraint("idempotency_key", name="uq_submission_idempotency"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_submission_source_external"),
    )
    op.create_index(op.f("ix_submissions_news_id"), "submissions", ["news_id"], unique=False)
    op.create_index(op.f("ix_submissions_source_id"), "submissions", ["source_id"], unique=False)
    op.create_index(op.f("ix_submissions_status"), "submissions", ["status"], unique=False)
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=True),
        sa.Column("news_id", sa.Uuid(), nullable=True),
        sa.Column("object_key", sa.String(length=1000), nullable=True),
        sa.Column("original_url", sa.String(length=2000), nullable=True),
        sa.Column("filename", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=200), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["news_id"], ["news.id"], name=op.f("fk_attachments_news_id_news"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_attachments_submission_id_submissions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachments")),
        sa.UniqueConstraint("object_key", name=op.f("uq_attachments_object_key")),
    )
    op.create_index(op.f("ix_attachments_news_id"), "attachments", ["news_id"], unique=False)
    op.create_index(
        op.f("ix_attachments_submission_id"), "attachments", ["submission_id"], unique=False
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=True),
        sa.Column("news_id", sa.Uuid(), nullable=True),
        sa.Column("classifier_id", sa.Uuid(), nullable=True),
        sa.Column("current_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner", sa.String(length=200), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "result",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["classifier_id"],
            ["classifiers.id"],
            name=op.f("fk_jobs_classifier_id_classifiers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["news_id"], ["news.id"], name=op.f("fk_jobs_news_id_news"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_jobs_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_available_at"), "jobs", ["available_at"], unique=False)
    op.create_index(
        "ix_jobs_claim", "jobs", ["kind", "status", "available_at", "lease_until"], unique=False
    )
    op.create_index(op.f("ix_jobs_kind"), "jobs", ["kind"], unique=False)
    op.create_index(op.f("ix_jobs_lease_until"), "jobs", ["lease_until"], unique=False)
    op.create_index(op.f("ix_jobs_news_id"), "jobs", ["news_id"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_submission_id"), "jobs", ["submission_id"], unique=False)
    op.create_table(
        "news_effective_labels",
        sa.Column("news_id", sa.Uuid(), nullable=False),
        sa.Column("facet_id", sa.Uuid(), nullable=False),
        sa.Column("value_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["facet_id"],
            ["facets.id"],
            name=op.f("fk_news_effective_labels_facet_id_facets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["news_id"],
            ["news.id"],
            name=op.f("fk_news_effective_labels_news_id_news"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["value_id"],
            ["facet_values.id"],
            name=op.f("fk_news_effective_labels_value_id_facet_values"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "news_id", "facet_id", "value_id", name=op.f("pk_news_effective_labels")
        ),
    )
    op.create_table(
        "news_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("news_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("facet_id", sa.Uuid(), nullable=False),
        sa.Column("value_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("origin_key", sa.String(length=200), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "evidence",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence between 0 and 1", name=op.f("ck_news_labels_confidence_range")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_news_labels_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["facet_id"],
            ["facets.id"],
            name=op.f("fk_news_labels_facet_id_facets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["news_id"], ["news.id"], name=op.f("fk_news_labels_news_id_news"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["value_id"],
            ["facet_values.id"],
            name=op.f("fk_news_labels_value_id_facet_values"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["news_versions.id"],
            name=op.f("fk_news_labels_version_id_news_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news_labels")),
        sa.UniqueConstraint(
            "news_id",
            "version_id",
            "value_id",
            "origin",
            "origin_key",
            name="uq_news_label_opinion",
        ),
    )
    op.create_index(op.f("ix_news_labels_facet_id"), "news_labels", ["facet_id"], unique=False)
    op.create_index(op.f("ix_news_labels_news_id"), "news_labels", ["news_id"], unique=False)
    op.create_index(op.f("ix_news_labels_value_id"), "news_labels", ["value_id"], unique=False)
    op.create_index(op.f("ix_news_labels_version_id"), "news_labels", ["version_id"], unique=False)
    op.create_table(
        "news_source_links",
        sa.Column("news_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["news_id"],
            ["news.id"],
            name=op.f("fk_news_source_links_news_id_news"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_news_source_links_submission_id_submissions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("news_id", "submission_id", name=op.f("pk_news_source_links")),
    )
    op.create_table(
        "processing_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("news_id", sa.Uuid(), nullable=True),
        sa.Column("version_id", sa.Uuid(), nullable=True),
        sa.Column("classifier_id", sa.Uuid(), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("callback_token_hash", sa.String(length=128), nullable=True),
        sa.Column("callback_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "request_payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("raw_request_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("raw_payload_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column(
            "validated_result",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "model",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("taxonomy_version", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("schema_version", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["classifier_id"],
            ["classifiers.id"],
            name=op.f("fk_processing_attempts_classifier_id_classifiers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_processing_attempts_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["news_id"],
            ["news.id"],
            name=op.f("fk_processing_attempts_news_id_news"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["news_versions.id"],
            name=op.f("fk_processing_attempts_version_id_news_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_attempts")),
        sa.UniqueConstraint(
            "callback_token_hash", name=op.f("uq_processing_attempts_callback_token_hash")
        ),
        sa.UniqueConstraint("job_id", "generation", name="uq_attempt_job_generation"),
    )
    op.create_index(
        op.f("ix_processing_attempts_job_id"), "processing_attempts", ["job_id"], unique=False
    )
    op.create_index(
        op.f("ix_processing_attempts_news_id"), "processing_attempts", ["news_id"], unique=False
    )
    op.create_table(
        "upload_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.String(length=200), nullable=False),
        sa.Column("temp_key", sa.String(length=1000), nullable=False),
        sa.Column("final_key", sa.String(length=1000), nullable=True),
        sa.Column("expected_size", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=200), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attachment_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name=op.f("fk_upload_intents_attachment_id_attachments"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_upload_intents")),
        sa.UniqueConstraint("final_key", name=op.f("uq_upload_intents_final_key")),
        sa.UniqueConstraint("temp_key", name=op.f("uq_upload_intents_temp_key")),
    )
    op.create_index(
        op.f("ix_upload_intents_owner_id"), "upload_intents", ["owner_id"], unique=False
    )
    op.create_index(op.f("ix_upload_intents_status"), "upload_intents", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_upload_intents_status"), table_name="upload_intents")
    op.drop_index(op.f("ix_upload_intents_owner_id"), table_name="upload_intents")
    op.drop_table("upload_intents")
    op.drop_index(op.f("ix_processing_attempts_news_id"), table_name="processing_attempts")
    op.drop_index(op.f("ix_processing_attempts_job_id"), table_name="processing_attempts")
    op.drop_table("processing_attempts")
    op.drop_table("news_source_links")
    op.drop_index(op.f("ix_news_labels_version_id"), table_name="news_labels")
    op.drop_index(op.f("ix_news_labels_value_id"), table_name="news_labels")
    op.drop_index(op.f("ix_news_labels_news_id"), table_name="news_labels")
    op.drop_index(op.f("ix_news_labels_facet_id"), table_name="news_labels")
    op.drop_table("news_labels")
    op.drop_table("news_effective_labels")
    op.drop_index(op.f("ix_jobs_submission_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_news_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_lease_until"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_kind"), table_name="jobs")
    op.drop_index("ix_jobs_claim", table_name="jobs")
    op.drop_index(op.f("ix_jobs_available_at"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_attachments_submission_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_news_id"), table_name="attachments")
    op.drop_table("attachments")
    op.drop_index(op.f("ix_submissions_status"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_source_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_news_id"), table_name="submissions")
    op.drop_table("submissions")
    op.drop_table("similarity_candidates")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_search_projections_status"), table_name="search_projections")
    op.drop_table("search_projections")
    op.drop_constraint("fk_news_current_version", "news", type_="foreignkey")
    op.drop_index(op.f("ix_news_versions_news_id"), table_name="news_versions")
    op.drop_table("news_versions")
    op.drop_index(op.f("ix_facet_values_facet_id"), table_name="facet_values")
    op.drop_table("facet_values")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("sources")
    op.drop_table("settings")
    op.drop_index(op.f("ix_outbox_events_topic"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_lease_until"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_delivered_at"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_available_at"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_aggregate_id"), table_name="outbox_events")
    op.drop_index("ix_outbox_claim", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index(op.f("ix_news_status"), table_name="news")
    op.drop_index(op.f("ix_news_published_at"), table_name="news")
    op.drop_table("news")
    op.drop_table("inbox_messages")
    op.drop_table("facets")
    op.drop_table("editorial_rules")
    op.drop_table("classifiers")
    op.drop_index(op.f("ix_audit_log_request_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_created_at"), table_name="audit_log")
    op.drop_table("audit_log")
