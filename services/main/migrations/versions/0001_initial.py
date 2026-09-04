"""Initial schema.

DDL берётся из моделей, а не пишется руками: на первой ревизии разойтись им
негде. Но список таблиц **заморожен** — и это важно.

Наивный `Base.metadata.create_all()` создавал бы и те таблицы, которые
появятся в моделях позже. На старой базе это незаметно, а на чистой первая же
ревизия создаёт таблицу из будущего, и следующая миграция падает с
`relation already exists`. Ровно так и случилось при первом развёртывании.

Поэтому здесь перечислено то, что существовало на момент этой ревизии.
Новая таблица — новая миграция, а этот список не трогаем.
"""

from __future__ import annotations

from alembic import op

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.db import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

#: Таблицы на момент первой ревизии. Не дополнять.
TABLES = (
    "users",
    "sessions",
    "sources",
    "api_keys",
    "facets",
    "facet_values",
    "news",
    "attachments",
    "news_labels",
    "news_effective_labels",
    "classifiers",
    "classification_jobs",
    "audit_log",
)


def _frozen():
    return [Base.metadata.tables[name] for name in TABLES]


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=_frozen())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=_frozen())
