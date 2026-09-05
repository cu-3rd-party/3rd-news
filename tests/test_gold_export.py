"""Золотой набор: флаг на новости, исключение из примеров, экспорт."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_news_has_is_gold_defaulting_to_false():
    from app.models import News

    column = News.__table__.columns["is_gold"]
    assert column.default.arg is False
    assert column.nullable is False


def test_migration_0003_adds_is_gold():
    path = ROOT / "services/main/migrations/versions/0003_news_is_gold.py"
    assert path.exists(), "миграция для is_gold не создана"
    text = path.read_text(encoding="utf-8")
    assert "is_gold" in text
    assert 'down_revision = "0002_settings"' in text


def _news(**overrides):
    """News в памяти, без БД — ровно то, что нужно _detail и export_record."""

    from datetime import datetime, timezone

    from app.models import News

    fields = dict(
        title="Заголовок",
        body_md="Тело",
        source_link=None,
        source_text="Деканат",
        lang="ru",
        published_at=datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc),
        received_at=datetime(2026, 4, 12, 9, 1, tzinfo=timezone.utc),
        status="published",
        dedup_hash="x" * 64,
        extra={},
        manual_facets=[],
        is_gold=False,
        classified_at=None,
    )
    fields.update(overrides)
    news = News(**fields)
    news.attachments = []
    news.labels = []
    news.effective_labels = []
    news.source = None
    return news


def test_detail_exposes_is_gold():
    from app.routers.admin_news import _detail

    assert _detail(_news(is_gold=True)).is_gold is True
    assert _detail(_news()).is_gold is False


def test_gold_in_defaults_to_marking():
    from app.schemas import GoldIn

    payload = GoldIn(ids=["a", "b"])
    assert payload.is_gold is True


def test_list_news_accepts_gold_filter():
    import inspect

    from app.routers.admin_news import list_news

    assert "gold" in inspect.signature(list_news).parameters


def _labelled_news():
    """Новость с ручными метками по двум осям и мнением классификатора."""

    import uuid

    from app.models import Attachment, Facet, FacetValue, NewsLabel, Source

    news = _news(manual_facets=["importance", "kind"], is_gold=True)
    news.source = Source(slug="time-anonsy", title="Анонсы", kind="mattermost")

    importance = Facet(id=uuid.uuid4(), slug="importance", title="Важность", type="single")
    kind = Facet(id=uuid.uuid4(), slug="kind", title="Тип", type="single")
    critical = FacetValue(id=uuid.uuid4(), facet_id=importance.id, slug="critical", title="Важно")
    event = FacetValue(id=uuid.uuid4(), facet_id=kind.id, slug="event", title="Мероприятие")

    manual = NewsLabel(origin="manual", origin_key="", confidence=1.0)
    manual.facet, manual.value = importance, critical
    robot = NewsLabel(origin="classifier", origin_key="regex", confidence=0.7)
    robot.facet, robot.value = kind, event
    news.labels = [manual, robot]

    poster = Attachment(
        kind="image",
        storage_path="2026/04/ab12_poster.jpg",
        mime="image/jpeg",
        filename="poster.jpg",
        caption=None,
        status="stored",
        position=0,
    )
    news.attachments = [poster]
    return news


def test_export_record_keeps_only_manual_labels_and_touched_facets():
    from app.export import export_record

    record = export_record(_labelled_news())
    # kind размечен руками как «нет значения»: ось есть, список пустой.
    assert record["labels"] == {"importance": ["critical"], "kind": []}
    assert record["manual_facets"] == ["importance", "kind"]
    assert record["is_gold"] is True


def test_export_record_carries_source_and_attachments():
    from app.export import export_record

    record = export_record(_labelled_news())
    assert record["source_key"] == "time-anonsy"
    assert record["attachments"] == [
        {
            "kind": "image",
            "path": "2026/04/ab12_poster.jpg",
            "mime": "image/jpeg",
            "filename": "poster.jpg",
            "caption": None,
        }
    ]
    assert record["published_at"] == "2026-04-12T09:00:00+00:00"


def test_export_record_is_json_serialisable():
    import json

    from app.export import export_record

    json.dumps(export_record(_labelled_news()), ensure_ascii=False)


def test_export_skips_rejected():
    from app.export import EXPORT_STATUSES

    assert "rejected" not in EXPORT_STATUSES
    assert "published" in EXPORT_STATUSES


def test_export_and_gold_routes_are_declared_before_the_id_route():
    from app.routers.admin_news import router

    paths = [route.path for route in router.routes]
    assert paths.index("/api/v1/admin/news/export") < paths.index("/api/v1/admin/news/{news_id}")
    assert paths.index("/api/v1/admin/news/gold") < paths.index("/api/v1/admin/news/{news_id}")


def test_export_can_dump_the_whole_corpus():
    import inspect

    from app.routers.admin_news import export_news

    params = inspect.signature(export_news).parameters
    assert "labelled" in params
    assert params["labelled"].default.default is True
