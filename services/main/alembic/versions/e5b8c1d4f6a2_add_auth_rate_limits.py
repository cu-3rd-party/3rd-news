from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5b8c1d4f6a2"
down_revision = "d4a7c9e12b3f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.create_table(
        "auth_rate_limits",
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "failure_count > 0",
            name=op.f("ck_auth_rate_limits_auth_rate_limit_failure_count"),
        ),
        sa.CheckConstraint(
            "scope IN ('account', 'ip')",
            name=op.f("ck_auth_rate_limits_auth_rate_limit_scope"),
        ),
        sa.PrimaryKeyConstraint("scope", "identifier_hash", name=op.f("pk_auth_rate_limits")),
    )
    op.create_index(
        op.f("ix_auth_rate_limits_updated_at"),
        "auth_rate_limits",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    context = op.get_context()
    if context.as_sql:
        context.impl.static_output("-- squawk-ignore-file ban-drop-table")
    op.drop_table("auth_rate_limits")
