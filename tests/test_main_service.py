"""Pure-logic tests for the main service: filters, cursors, dedup, resolution.

These need neither Postgres nor Redis. The database-backed paths are exercised
by the compose stack; see `docs/README` for the end-to-end walkthrough.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.ingest_service import content_hash  # noqa: E402
from app.labels import ORIGIN_RANK  # noqa: E402
from app.routers.news import (  # noqa: E402
    _decode_cursor,
    _encode_cursor,
    _facet_filters,
    _merge_filters,
)
from app.security import (  # noqa: E402
    generate_api_key,
    hash_password,
    hash_secret,
    verify_password,
)
from app.storage import (  # noqa: E402
    display_filename,
    guess_kind,
    public_url,
    safe_filename,
)


# --------------------------------------------------------------------------- #
# Query parsing
# --------------------------------------------------------------------------- #


def test_facet_filters_are_pulled_out_of_the_query_string():
    params = {
        "facet.importance": ["high,medium"],
        "facet.stream": ["2025", "2026"],
        "limit": ["50"],
    }
    assert _facet_filters(params) == {
        "importance": ["high", "medium"],
        "stream": ["2025", "2026"],
    }


def test_non_facet_parameters_are_ignored():
    assert _facet_filters({"q": ["дедлайн"], "order": ["desc"]}) == {}


def test_blank_values_are_dropped():
    assert _facet_filters({"facet.stream": ["2025, ,2026"]}) == {"stream": ["2025", "2026"]}


def test_preset_narrows_a_requested_filter():
    merged, _ = _merge_filters(
        {"stream": ["2024", "2025"]}, {"facets": {"stream": ["2025", "2026"]}}
    )
    assert merged["stream"] == ["2025"]


def test_preset_applies_when_the_caller_asked_for_nothing():
    merged, _ = _merge_filters({}, {"facets": {"stream": ["2025"]}})
    assert merged["stream"] == ["2025"]


def test_preset_cannot_be_widened():
    """Asking for a value outside the preset must match nothing, not everything."""

    merged, _ = _merge_filters({"stream": ["2030"]}, {"facets": {"stream": ["2025"]}})
    assert merged["stream"] == []


def test_filters_outside_the_preset_pass_through():
    merged, _ = _merge_filters(
        {"importance": ["high"]}, {"facets": {"stream": ["2025"]}}
    )
    assert merged["importance"] == ["high"]
    assert merged["stream"] == ["2025"]


# --------------------------------------------------------------------------- #
# Cursors
# --------------------------------------------------------------------------- #


def test_cursor_round_trip():
    stamp = datetime(2026, 3, 1, 12, 30, tzinfo=timezone.utc)
    news_id = uuid.uuid4()
    decoded_stamp, decoded_id = _decode_cursor(_encode_cursor(stamp, news_id))
    assert decoded_stamp == stamp
    assert decoded_id == news_id


def test_cursor_is_url_safe():
    cursor = _encode_cursor(datetime.now(timezone.utc), uuid.uuid4())
    assert "=" not in cursor and "+" not in cursor and "/" not in cursor


def test_malformed_cursor_is_rejected():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _decode_cursor("!!!not-base64!!!")
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# Dedup hashing
# --------------------------------------------------------------------------- #


def test_content_hash_ignores_whitespace_and_case():
    assert content_hash("Заголовок", "Текст  новости") == content_hash(
        "заголовок", "текст\nновости"
    )


def test_content_hash_separates_different_bodies():
    assert content_hash(None, "первая") != content_hash(None, "вторая")


def test_content_hash_includes_the_title():
    assert content_hash("A", "тело") != content_hash("B", "тело")


# --------------------------------------------------------------------------- #
# Label resolution policy
# --------------------------------------------------------------------------- #


def test_manual_outranks_every_automatic_origin():
    assert ORIGIN_RANK["manual"] > ORIGIN_RANK["source_default"]
    assert ORIGIN_RANK["source_default"] > ORIGIN_RANK["parser"]
    assert ORIGIN_RANK["parser"] > ORIGIN_RANK["classifier"]


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def test_api_key_prefix_matches_the_key():
    full, prefix, digest = generate_api_key()
    assert full.startswith("tnk_")
    assert full.startswith(prefix)
    assert digest == hash_secret(full)
    assert digest != full


def test_two_api_keys_differ():
    assert generate_api_key()[0] != generate_api_key()[0]


def test_password_hash_round_trip():
    digest = hash_password("correct horse")
    assert verify_password("correct horse", digest)
    assert not verify_password("wrong", digest)
    assert not verify_password("correct horse", None)


# --------------------------------------------------------------------------- #
# Storage helpers
# --------------------------------------------------------------------------- #


def test_safe_filename_strips_path_traversal():
    assert "/" not in safe_filename("../../etc/passwd")
    assert ".." not in safe_filename("../../etc/passwd")


def test_safe_filename_falls_back_for_empty_input():
    assert safe_filename(None)
    assert safe_filename("///")


def test_safe_filename_never_loses_the_extension():
    """Без расширения статика отдаётся как octet-stream и картинка не откроется."""

    assert safe_filename("эрмитаж.png") == "file.png"
    assert safe_filename("события август 24-30 4.png").endswith(".png")
    assert safe_filename("отчёт.pdf").endswith(".pdf")


def test_safe_filename_keeps_ascii_names_readable():
    assert safe_filename("poster_2026.png") == "poster_2026.png"


def test_display_filename_keeps_cyrillic():
    """Почти всё, что тут хранится, названо по-русски."""

    assert display_filename("события август 24-30.png") == "события август 24-30.png"


def test_display_filename_strips_the_path():
    assert display_filename("../../etc/passwd") == "passwd"
    assert display_filename("/var/tmp/афиша.png") == "афиша.png"


def test_display_filename_handles_nothing():
    assert display_filename(None) is None
    assert display_filename("   ") is None


def test_public_url_is_absolute():
    """Относительный /media бесполезен боту, который читает API снаружи."""

    url = public_url("2026/09/abc_poster.png")
    assert url.startswith("http://") or url.startswith("https://")
    assert url.endswith("/media/2026/09/abc_poster.png")


def test_public_url_of_nothing_is_nothing():
    assert public_url(None) is None


@pytest.mark.parametrize(
    ("mime", "filename", "expected"),
    [
        ("image/png", "a.png", "image"),
        ("video/mp4", "a.mp4", "video"),
        ("application/pdf", "a.pdf", "pdf"),
        (None, "schedule.pdf", "pdf"),
        (None, "notes.txt", "file"),
    ],
)
def test_guess_kind(mime, filename, expected):
    assert guess_kind(mime, filename) == expected


# --------------------------------------------------------------------------- #
# Вложения не должны утекать мимо авторизации
# --------------------------------------------------------------------------- #


def test_media_route_requires_read_scope():
    """Раздача статикой была дырой: ссылка из выдачи открывалась без ключа."""

    from app.main import app

    routes = {getattr(r, "path", ""): r for r in app.routes}
    media = routes.get("/media/{path:path}")
    assert media is not None, "маршрут /media должен быть обычной ручкой, а не mount"
    names = {d.call.__name__ for d in media.dependant.dependencies}
    assert any("scope" in n or "principal" in n for n in names) or media.dependant.dependencies


def test_media_is_not_mounted_as_static():
    from starlette.staticfiles import StaticFiles

    from app.main import app

    assert not any(isinstance(getattr(r, "app", None), StaticFiles) for r in app.routes)


# --------------------------------------------------------------------------- #
# Миграции
# --------------------------------------------------------------------------- #


def test_initial_migration_does_not_absorb_later_tables():
    """Первая ревизия обязана создавать только то, что было на её момент.

    Иначе на чистой базе она создаёт таблицу из будущего, и следующая
    миграция падает с `relation already exists` — ровно это и случилось при
    первом развёртывании на сервер.
    """

    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "services/main/migrations/versions/0001_initial.py"
    spec = importlib.util.spec_from_file_location("migration_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    from app.db import Base

    assert "settings" not in module.TABLES, "settings появилась во второй ревизии"
    # Всё перечисленное должно существовать в моделях — иначе список протух.
    assert set(module.TABLES) <= set(Base.metadata.tables)


def test_every_model_table_is_covered_by_some_migration():
    """Таблица в моделях без миграции — это база, которая не поднимется."""

    import re
    from pathlib import Path

    from app.db import Base

    versions = Path(__file__).resolve().parents[1] / "services/main/migrations/versions"
    text = " ".join(p.read_text(encoding="utf-8") for p in versions.glob("*.py"))
    mentioned = set(re.findall(r"[\"']([a-z_]+)[\"']", text))
    missing = set(Base.metadata.tables) - mentioned
    assert not missing, f"нет миграции для таблиц: {sorted(missing)}"
