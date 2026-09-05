"""Флаг золотой новости: эталон для измерения классификаторов.

Revision ID: 0003_news_is_gold
Revises: 0002_settings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_news_is_gold"
down_revision = "0002_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news",
        sa.Column("is_gold", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("news", "is_gold")
