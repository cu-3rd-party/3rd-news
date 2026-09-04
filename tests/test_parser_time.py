"""Парсер TiMe: разбор постов Mattermost.

Фикстура `fixtures/time_posts.json` синтетическая, но повторяет форму ответа
живого канала «Анонсы ЦУ»: те же поля, те же типы, и по посту на каждый
случай, который там реально встречается — объявление с жирным заголовком и
эмодзи, пост из одной картинки без текста, ответ в треде, системный пост,
удалённый пост и пост от вебхука.
"""

from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

import httpx
import pytest
from thirdnews_contracts import AttachmentKind

from .conftest import time_client as client_module
from .conftest import time_parser as parser

ChannelRef = client_module.ChannelRef
TimeAuthError = client_module.TimeAuthError

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "time_posts.json").read_text(encoding="utf-8")
)
POSTS = {post_id: FIXTURE["posts"][post_id] for post_id in FIXTURE["order"]}

REF = ChannelRef(team="tsentralnyy-universitet", channel="anonsy-tsu")


# --------------------------------------------------------------------------- #
# Разбор ссылки на канал
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    [
        "https://time.cu.ru/tsentralnyy-universitet/channels/anonsy-tsu",
        "http://time.cu.ru/tsentralnyy-universitet/channels/anonsy-tsu",
        "/tsentralnyy-universitet/channels/anonsy-tsu",
        "tsentralnyy-universitet/anonsy-tsu",
        "  tsentralnyy-universitet/anonsy-tsu  ",
    ],
)
def test_channel_ref_parses_every_shape(value):
    assert ChannelRef.parse(value) == REF


def test_channel_ref_slug_is_stable():
    assert REF.slug == "time-tsentralnyy-universitet-anonsy-tsu"


@pytest.mark.parametrize("value", ["", "   ", "просто-канал", "a/b/c/d"])
def test_channel_ref_rejects_garbage(value):
    with pytest.raises(ValueError):
        ChannelRef.parse(value)


# --------------------------------------------------------------------------- #
# Что считаем новостью
# --------------------------------------------------------------------------- #


def test_announcement_is_newsworthy():
    assert parser.is_newsworthy(POSTS["post_announcement"])


def test_reply_is_skipped_by_default():
    """Ответы в тредах — это вопросы студентов под анонсом, а не анонсы."""

    assert not parser.is_newsworthy(POSTS["post_reply"])
    assert parser.is_newsworthy(POSTS["post_reply"], include_replies=True)


def test_system_post_is_skipped():
    assert not parser.is_newsworthy(POSTS["post_system"])


def test_deleted_post_is_skipped():
    assert not parser.is_newsworthy(POSTS["post_deleted"])


def test_image_only_post_is_kept():
    """Афиша без подписи — полноценный анонс, терять её нельзя."""

    assert parser.is_newsworthy(POSTS["post_image_only"])


def test_post_without_text_and_files_is_skipped():
    assert not parser.is_newsworthy({"id": "x", "message": "   ", "metadata": {}})


# --------------------------------------------------------------------------- #
# Текст и заголовок
# --------------------------------------------------------------------------- #


def test_body_is_the_raw_markdown():
    body = parser.post_body(POSTS["post_announcement"])
    assert body.startswith("**Стартуем в новый учебный год**")
    assert "Расписание уже в личном кабинете." in body


def test_webhook_text_is_pulled_out_of_props():
    body = parser.post_body(POSTS["post_webhook"])
    assert "Изменение в расписании" in body
    assert "Лекция перенесена" in body
    assert "аудиторию 402" in body


def test_webhook_fallback_does_not_duplicate_text():
    body = parser.post_body(POSTS["post_webhook"])
    assert body.count("аудиторию 402") == 1


def test_title_strips_markdown_and_emoji():
    title = parser.guess_title(parser.post_body(POSTS["post_announcement"]))
    assert title == "Стартуем в новый учебный год"


def test_single_line_post_gets_no_title():
    """Иначе заголовок просто продублировал бы тело."""

    assert parser.guess_title(parser.post_body(POSTS["post_oneliner"])) is None


def test_long_first_line_is_not_a_title():
    body = "а" * 200 + "\n\nвторая строка"
    assert parser.guess_title(body) is None


def test_title_keeps_time_ranges_intact():
    """`:cu-hat:` — эмодзи, а `18:00` — нет."""

    assert parser.guess_title("Встреча в 18:00\n\nПодробности ниже") == "Встреча в 18:00"


def test_title_strips_heading_markers():
    assert parser.guess_title("### Важно\n\nтекст") == "Важно"


def test_title_drops_a_dangling_comma():
    """`***Успеха, радости, везения***,` — автор продолжил фразу ниже."""

    assert parser.guess_title("***Успеха, радости***,\n\nи всего такого") == "Успеха, радости"


def test_title_keeps_question_and_exclamation():
    assert parser.guess_title("**Лето с пользой? Легко!**\n\nтекст") == "Лето с пользой? Легко!"


def test_title_keeps_internal_colon():
    body = "**Как провести июль: запишись на буткемпы**\n\nтекст"
    assert parser.guess_title(body) == "Как провести июль: запишись на буткемпы"


# --------------------------------------------------------------------------- #
# Сборка новости
# --------------------------------------------------------------------------- #


def submission(post_id: str):
    return parser.post_to_submission(
        POSTS[post_id],
        ref=REF,
        channel_title="Анонсы ЦУ",
        base_url="https://time.cu.ru",
        author="Иван Иванов",
    )


def test_announcement_maps_onto_a_submission():
    item = submission("post_announcement")
    assert item is not None
    assert item.external_id == "post_announcement"
    assert item.source_key == REF.slug
    assert item.title == "Стартуем в новый учебный год"
    assert item.source_text == "Анонсы ЦУ, TiMe"
    assert str(item.source_link) == "https://time.cu.ru/tsentralnyy-universitet/pl/post_announcement"
    assert item.lang == "ru"


def test_published_at_comes_from_create_at():
    item = submission("post_announcement")
    assert item.published_at.tzinfo is not None
    assert item.published_at.astimezone(timezone.utc).year == 2026


def test_edited_post_records_when_it_was_edited():
    assert "edited_at" in submission("post_announcement").extra


def test_extra_carries_channel_and_author():
    extra = submission("post_announcement").extra
    assert extra["parser"] == "time"
    assert extra["channel"] == "anonsy-tsu"
    assert extra["team"] == "tsentralnyy-universitet"
    assert extra["author"] == "Иван Иванов"


def test_attachments_are_sent_as_uploads_not_links():
    """`/api/v4/files/...` требует куки, по ссылке сервис ничего не скачает."""

    item = submission("post_announcement")
    assert len(item.attachments) == 1
    attachment = item.attachments[0]
    assert attachment.url is None
    assert attachment.upload_name == "file_0"
    assert attachment.kind == AttachmentKind.IMAGE
    assert attachment.filename == "афиша сентябрь.png"


def test_skipped_posts_produce_nothing():
    for post_id in ("post_reply", "post_system", "post_deleted"):
        assert submission(post_id) is None


def test_image_only_post_survives_with_its_file():
    item = submission("post_image_only")
    assert item is not None
    assert item.title is None
    assert len(item.attachments) == 1


def test_two_image_only_posts_stay_distinct():
    """Тела одинаково пустые, но external_id разные — это разные новости."""

    other = dict(POSTS["post_image_only"], id="post_image_only_2")
    first = submission("post_image_only")
    second = parser.post_to_submission(other, ref=REF, channel_title="Анонсы ЦУ")
    assert first.external_id != second.external_id


@pytest.mark.parametrize(
    ("mime", "extension", "expected"),
    [
        ("image/png", "png", AttachmentKind.IMAGE),
        ("video/mp4", "mp4", AttachmentKind.VIDEO),
        ("application/pdf", "pdf", AttachmentKind.PDF),
        ("audio/mpeg", "mp3", AttachmentKind.AUDIO),
        (None, "pdf", AttachmentKind.PDF),
        (None, "docx", AttachmentKind.FILE),
        ("", "", AttachmentKind.FILE),
    ],
)
def test_attachment_kind(mime, extension, expected):
    assert parser.attachment_kind(mime, extension) == expected


# --------------------------------------------------------------------------- #
# Клиент
# --------------------------------------------------------------------------- #


def build_client(handler) -> object:
    return client_module.TimeClient(
        base_url="https://time.cu.ru",
        cookie="MMAUTHTOKEN=test",
        transport=httpx.MockTransport(handler),
    )


def test_client_requires_some_credential():
    with pytest.raises(TimeAuthError):
        client_module.TimeClient(base_url="https://time.cu.ru")


def test_expired_cookies_say_so_clearly():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Invalid or expired session"})

    with build_client(handler) as time:
        with pytest.raises(TimeAuthError, match="протухли"):
            time.whoami()


def test_resolve_channel_walks_team_then_channel():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/teams/name/tsentralnyy-universitet"):
            return httpx.Response(200, json={"id": "team1", "display_name": "ЦУ"})
        return httpx.Response(
            200, json={"id": "chan1", "name": "anonsy-tsu", "display_name": "Анонсы ЦУ"}
        )

    with build_client(handler) as time:
        channel = time.resolve_channel(REF)

    assert channel["display_name"] == "Анонсы ЦУ"
    assert channel["team"]["id"] == "team1"
    assert seen == [
        "/api/v4/teams/name/tsentralnyy-universitet",
        "/api/v4/teams/team1/channels/name/anonsy-tsu",
    ]


def test_fetch_posts_follows_order_not_dict_order():
    """`posts` — словарь, порядок живёт только в `order`."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"order": FIXTURE["order"], "posts": FIXTURE["posts"]})

    with build_client(handler) as time:
        posts = time.fetch_posts("chan1", per_page=60, max_pages=1)

    assert [post["id"] for post in posts] == FIXTURE["order"]


def test_fetch_posts_stops_on_a_short_page():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"order": ["post_oneliner"], "posts": POSTS})

    with build_client(handler) as time:
        time.fetch_posts("chan1", per_page=60, max_pages=5)

    assert calls["n"] == 1


def test_fetch_posts_pages_until_the_limit():
    calls = {"n": 0}
    full = FIXTURE["order"]

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"order": full, "posts": FIXTURE["posts"]})

    with build_client(handler) as time:
        posts = time.fetch_posts("chan1", per_page=len(full), max_pages=3)

    assert calls["n"] == 3
    assert len(posts) == len(full) * 3


def test_download_file_refuses_oversized_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5000)

    with build_client(handler) as time:
        assert time.download_file("file_poster", max_bytes=100) is None
        assert time.download_file("file_poster", max_bytes=10_000) == b"x" * 5000


def test_parse_channels_skips_broken_entries(caplog):
    refs = parser.parse_channels(
        "https://time.cu.ru/tsentralnyy-universitet/channels/anonsy-tsu, ,мусор"
    )
    assert refs == [REF]
