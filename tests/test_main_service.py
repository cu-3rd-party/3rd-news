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
from app.storage import guess_kind, safe_filename  # noqa: E402


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
