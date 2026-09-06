from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4a7c9e12b3f"
down_revision = "bc8bbbb844d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.create_table(
        "manual_label_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("news_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("facet_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
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
            "action in ('set','release')",
            name=op.f("ck_manual_label_decisions_manual_decision_action"),
        ),
        sa.CheckConstraint(
            "origin in ('manual','provenance')",
            name=op.f("ck_manual_label_decisions_manual_decision_origin"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_manual_label_decisions_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["facet_id"],
            ["facets.id"],
            name=op.f("fk_manual_label_decisions_facet_id_facets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["news_id"],
            ["news.id"],
            name=op.f("fk_manual_label_decisions_news_id_news"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["news_versions.id"],
            name=op.f("fk_manual_label_decisions_version_id_news_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_label_decisions")),
        sa.UniqueConstraint(
            "news_id",
            "version_id",
            "facet_id",
            "revision",
            name="uq_manual_decision_revision",
        ),
    )
    op.create_index(
        "ix_manual_decision_latest",
        "manual_label_decisions",
        ["news_id", "version_id", "facet_id", "revision"],
        unique=False,
    )
    op.create_index(
        op.f("ix_manual_label_decisions_facet_id"),
        "manual_label_decisions",
        ["facet_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_manual_label_decisions_news_id"),
        "manual_label_decisions",
        ["news_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_manual_label_decisions_version_id"),
        "manual_label_decisions",
        ["version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.drop_index(op.f("ix_manual_label_decisions_version_id"), table_name="manual_label_decisions")
    op.drop_index(op.f("ix_manual_label_decisions_news_id"), table_name="manual_label_decisions")
    op.drop_index(op.f("ix_manual_label_decisions_facet_id"), table_name="manual_label_decisions")
    op.drop_index("ix_manual_decision_latest", table_name="manual_label_decisions")
    op.drop_table("manual_label_decisions")
