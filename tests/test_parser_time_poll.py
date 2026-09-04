"""Проход парсера по каналу целиком — с настоящей фильтрацией авторов.

Эти тесты появились из-за живой ошибки: локальный кэш имён авторов назывался
`authors` и затенял одноимённый параметр, решающий, чьи посты брать. Питон на
это не ругается, тесты на чистых функциях тоже — фильтр просто молча
переставал работать, и в ленту возвращались вопросы студентов.
"""

from __future__ import annotations

import httpx
import pytest

from .conftest import time_client as client_module
from .conftest import time_parser as parser

ChannelRef = client_module.ChannelRef
REF = ChannelRef(team="tsentralnyy-universitet", channel="anonsy-tsu")

CURATOR = "user_curator"
STUDENT = "user_student"


def post(post_id: str, user_id: str, message: str) -> dict:
    return {
        "id": post_id,
        "user_id": user_id,
        "message": message,
        "create_at": 1788266446965,
        "edit_at": 0,
        "delete_at": 0,
        "root_id": "",
        "type": "",
        "props": {},
        "metadata": {},
    }


POSTS = [
    post("p1", CURATOR, "### Выбор курсов закрывается через 40 минут\n\nУспейте до 14:00."),
    post("p2", STUDENT, "а когда откроется запись на пары?"),
    post("p3", STUDENT, "Куда прислать справку для физкультуры?"),
    post("p4", CURATOR, "### Маяк теперь доступен в TiMe\n\nЕдиная точка для обращений."),
]

ROLES = {
    CURATOR: {"channel_user", "channel_admin"},
    STUDENT: {"channel_user"},
}


class FakeTime:
    """Ровно та часть TimeClient, которой пользуется `poll_channel`."""

    base_url = "https://time.cu.ru"

    def __init__(self) -> None:
        self.role_lookups = 0

    def resolve_channel(self, ref):
        return {"id": "chan1", "display_name": "Анонсы ЦУ"}

    def fetch_posts(self, channel_id, per_page, max_pages):
        return POSTS

    def channel_member_roles(self, channel_id, user_id):
        self.role_lookups += 1
        return ROLES[user_id]

    def user_display_name(self, user_id):
        return "Куратор" if user_id == CURATOR else "Студент"


class FakeNews:
    """Приём новостей: запоминает, что до него дошло."""

    def __init__(self) -> None:
        self.submitted: list = []

    def submit(self, submission, files=None):
        self.submitted.append(submission)

        class Result:
            status = type("S", (), {"value": "created"})()

        return Result()


def run(authors: str | None):
    time_client, news = FakeTime(), FakeNews()
    created, duplicates, skipped = parser.poll_channel(
        time_client, news, REF, max_age_days=3650, authors=authors
    )
    return time_client, news, created, skipped


def test_privileged_mode_keeps_only_the_curator():
    _time, news, created, skipped = run("privileged")

    assert [s.external_id for s in news.submitted] == ["p1", "p4"]
    assert created == 2
    assert skipped == 2


def test_all_mode_keeps_everything():
    """Режим для каналов, где объявления публикует обычный участник."""

    _time, news, created, skipped = run("all")

    assert [s.external_id for s in news.submitted] == ["p1", "p2", "p3", "p4"]
    assert created == 4
    assert skipped == 0


def test_student_questions_never_reach_the_feed_in_privileged_mode():
    _time, news, _created, _skipped = run("privileged")
    bodies = " ".join(s.body_md for s in news.submitted)
    assert "запись на пары" not in bodies
    assert "справку для физкультуры" not in bodies


def test_roles_are_looked_up_once_per_author():
    """Авторов единицы, постов сотни — иначе это лишние запросы к TiMe."""

    time_client, _news, _created, _skipped = run("privileged")
    assert time_client.role_lookups == 2


def test_all_mode_asks_for_no_roles_at_all():
    time_client, _news, _created, _skipped = run("all")
    assert time_client.role_lookups == 0


@pytest.mark.parametrize("mode", ["privileged", "all"])
def test_author_name_still_lands_in_extra(mode):
    """Кэш имён и режим отбора — разные вещи; когда-то они звались одинаково."""

    _time, news, _created, _skipped = run(mode)
    assert news.submitted[0].extra["author"] == "Куратор"


def test_transport_level_client_matches_the_fake():
    """Страховка, что FakeTime не разошёлся с настоящим клиентом."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"roles": "channel_user channel_admin"})

    with client_module.TimeClient(
        base_url="https://time.cu.ru",
        cookie="MMAUTHTOKEN=test",
        transport=httpx.MockTransport(handler),
    ) as real:
        assert real.channel_member_roles("chan1", CURATOR) == ROLES[CURATOR]
