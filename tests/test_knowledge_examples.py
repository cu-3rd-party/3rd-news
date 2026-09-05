"""Примеры для классификаторов: только ручные, только не золотые."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.knowledge import examples_query


def _sql(query) -> str:
    return str(
        query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def test_examples_exclude_gold_news():
    sql = _sql(examples_query(limit=8))
    assert "news.is_gold IS false" in sql


def test_examples_are_manual_only():
    sql = _sql(examples_query(limit=8))
    assert "news_labels.origin = 'manual'" in sql


def test_examples_exclude_the_item_being_classified():
    news_id = uuid.uuid4()
    sql = _sql(examples_query(limit=8, exclude_news_id=news_id))
    assert f"news.id != '{news_id}'" in sql
