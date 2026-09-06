from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

import pytest
from thirdnews_contracts import AttachmentKind

from lib.domain.entities.channel_ref import ChannelRef
from lib.domain.entities.roles import has_posting_privileges
from lib.infra.clients.time import TimeClient
from lib.interactor.errors.time_auth import TimeAuthError
from lib.interactor.use_cases.post_conversion import (
    attachment_kind,
    guess_title,
    is_newsworthy,
    parse_channels,
    post_body,
    post_to_submission,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "time_posts.json").read_text(encoding="utf-8")
)
POSTS = {post_id: FIXTURE["posts"][post_id] for post_id in FIXTURE["order"]}
REF = ChannelRef(team="tsentralnyy-universitet", channel="anonsy-tsu")


@pytest.mark.parametrize(
    "value",
    [
        "https://time.cu.ru/tsentralnyy-universitet/channels/anonsy-tsu",
        "/tsentralnyy-universitet/channels/anonsy-tsu",
        "tsentralnyy-universitet/anonsy-tsu",
    ],
)
def test_channel_ref_accepts_supported_shapes(value: str) -> None:
    assert ChannelRef.parse(value) == REF
    assert REF.slug == "time-tsentralnyy-universitet-anonsy-tsu"


@pytest.mark.parametrize("value", ["", "просто-канал", "a/b/c/d"])
def test_channel_ref_rejects_ambiguous_shapes(value: str) -> None:
    with pytest.raises(ValueError):
        ChannelRef.parse(value)


def test_client_requires_credentials() -> None:
    with pytest.raises(TimeAuthError):
        TimeClient()


@pytest.mark.parametrize(
    ("roles", "expected"),
    [
        ({"channel_user"}, False),
        ({"channel_user", "channel_guest"}, False),
        ({"channel_user", "channel_admin"}, True),
        ({"custom-scheme-role"}, True),
        (set(), False),
    ],
)
def test_privileged_author_rule(roles: set[str], expected: bool) -> None:
    assert has_posting_privileges(roles) is expected


def test_deleted_system_reply_and_empty_posts_are_rejected() -> None:
    assert not is_newsworthy(POSTS["post_deleted"])
    assert not is_newsworthy(POSTS["post_system"])
    assert not is_newsworthy(POSTS["post_reply"])
    assert is_newsworthy(POSTS["post_reply"], include_replies=True)
    assert not is_newsworthy({"message": " ", "metadata": {}})


def test_image_only_post_is_preserved() -> None:
    assert is_newsworthy(POSTS["post_image_only"])
    item = post_to_submission(POSTS["post_image_only"], ref=REF, channel_title="Анонсы")
    assert item is not None
    assert item.external_id == "post_image_only"
    assert item.body_md == ""


def test_webhook_body_is_extracted_without_duplicate_fallback() -> None:
    body = post_body(POSTS["post_webhook"])
    assert "Изменение в расписании" in body
    assert body.count("аудиторию 402") == 1


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Встреча в 18:00\n\nПодробности ниже", "Встреча в 18:00"),
        ("### Важно\n\nтекст", "Важно"),
        ("***Успеха, радости***,\n\nи всего такого", "Успеха, радости"),
        ("**Лето с пользой? Легко!**\n\nтекст", "Лето с пользой? Легко!"),
        ("одна строка", None),
        ("а" * 200 + "\n\nтекст", None),
    ],
)
def test_title_boundaries(body: str, expected: str | None) -> None:
    assert guess_title(body) == expected


def test_submission_maps_identity_permalink_time_and_provenance() -> None:
    item = post_to_submission(
        POSTS["post_announcement"],
        ref=REF,
        channel_title="Анонсы ЦУ",
        base_url="https://time.cu.ru",
        author="Иван Иванов",
    )
    assert item is not None
    assert (item.source, item.external_id, item.lang) == (REF.slug, "post_announcement", "ru")
    assert str(item.source_link).endswith("/tsentralnyy-universitet/pl/post_announcement")
    assert item.published_at is not None and item.published_at.astimezone(UTC).year == 2026
    assert item.extra["author"] == "Иван Иванов"
    assert "edited_at" in item.extra


@pytest.mark.parametrize(
    ("mime", "extension", "expected"),
    [
        ("image/png", "png", AttachmentKind.IMAGE),
        ("video/mp4", "mp4", AttachmentKind.VIDEO),
        ("application/pdf", "pdf", AttachmentKind.PDF),
        ("audio/mpeg", "mp3", AttachmentKind.AUDIO),
        (None, "pdf", AttachmentKind.PDF),
        (None, "docx", AttachmentKind.FILE),
    ],
)
def test_attachment_kinds(
    mime: str | None, extension: str | None, expected: AttachmentKind
) -> None:
    assert attachment_kind(mime, extension) is expected


def test_parse_channels_skips_bad_entries() -> None:
    assert parse_channels(
        "https://time.cu.ru/tsentralnyy-universitet/channels/anonsy-tsu, мусор"
    ) == [REF]


@pytest.mark.asyncio
async def test_post_paging_uses_order_and_stops_on_short_page(monkeypatch) -> None:
    client = TimeClient(cookie="MMAUTHTOKEN=test")
    calls: list[int] = []

    async def get_json(_path: str, **params: Any) -> dict[str, Any]:
        calls.append(params["page"])
        return {"order": ["b", "a"], "posts": {"a": {"id": "a"}, "b": {"id": "b"}}}

    monkeypatch.setattr(client, "get_json", get_json)
    posts = await client.fetch_posts("channel", per_page=3, max_pages=8)
    assert [item["id"] for item in posts] == ["b", "a"]
    assert calls == [0]


@pytest.mark.asyncio
async def test_channel_paging_filters_direct_and_group_messages(monkeypatch) -> None:
    client = TimeClient(token="token")
    pages = [
        [{"name": "public", "type": "O"}, {"name": "dm", "type": "D"}],
        [{"name": "private", "type": "P"}],
    ]

    async def get_json(_path: str, **params: Any) -> list[dict[str, str]]:
        return pages[params["page"]]

    monkeypatch.setattr(client, "get_json", get_json)
    result = await client.list_public_channels("team", per_page=2, max_pages=5)
    assert [item["name"] for item in result] == ["public", "private"]
