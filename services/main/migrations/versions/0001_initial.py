"""Initial schema.

Built straight from the models rather than hand-written DDL: this is the first
revision, so the two cannot drift, and every later revision is a normal
`alembic revision --autogenerate` diff against it.
"""

from __future__ import annotations

from alembic import op

from app.db import Base
from app import models  # noqa: F401  (registers the tables on Base.metadata)

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
