"""Перечисление и выбор каналов TiMe.

Главное, что здесь проверяется: **личные переписки не могут попасть в
парсер**. У обычного аккаунта в ЦУ их шестьдесят штук вперемешку с рабочими
каналами, и один пропущенный фильтр по типу означал бы личную переписку в
публичной новостной ленте.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from .conftest import time_client as client_module

ChannelRef = client_module.ChannelRef
TimeClient = client_module.TimeClient

TEAM = {"id": "team1", "name": "tsentralnyy-universitet", "display_name": "ЦУ"}


def channel(name: str, ctype: str = "O", **extra) -> dict:
    base = {
        "id": f"id-{name}",
        "name": name,
        "display_name": name.replace("-", " ").title(),
        "type": ctype,
        "team_id": "team1",
        "total_msg_count": 10,
        "last_post_at": 1788266446965,
        "delete_at": 0,
        "purpose": "",
    }
    base.update(extra)
    return base


def build_client(handler):
    return TimeClient(
        base_url="https://time.cu.ru",
        cookie="MMAUTHTOKEN=test",
        transport=httpx.MockTransport(handler),
    )


# --------------------------------------------------------------------------- #
# Личные переписки
# --------------------------------------------------------------------------- #


def test_joined_channels_drop_direct_messages():
    """Ровно та ситуация с живого аккаунта: 59 личных среди рабочих."""

    mixed = (
        [channel(f"dm-{i}", "D") for i in range(59)]
        + [channel(f"public-{i}", "O") for i in range(35)]
        + [channel(f"private-{i}", "P") for i in range(5)]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mixed)

    with build_client(handler) as time:
        result = time.list_joined_channels("team1")

    assert len(result) == 40
    assert {c["type"] for c in result} == {"O", "P"}
    assert not any(c["type"] in {"D", "G"} for c in result)


def test_group_messages_are_dropped_too():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[channel("group", "G"), channel("real", "O")])

    with build_client(handler) as time:
        assert [c["name"] for c in time.list_joined_channels("team1")] == ["real"]


def test_public_listing_also_filters_types():
    """На случай, если сервер когда-нибудь начнёт подмешивать личные сюда."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[channel("dm", "D"), channel("ok", "O")])

    with build_client(handler) as time:
        assert [c["name"] for c in time.list_public_channels("team1", per_page=200)] == ["ok"]


# --------------------------------------------------------------------------- #
# Постраничный обход
# --------------------------------------------------------------------------- #


def test_public_channels_walk_every_page():
    """В ЦУ 1633 канала — одной страницей их не забрать."""

    pages = [[channel(f"c{p}-{i}") for i in range(200)] for p in range(8)]
    pages.append([channel("last")])
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", 0))
        seen.append(page)
        return httpx.Response(200, json=pages[page] if page < len(pages) else [])

    with build_client(handler) as time:
        result = time.list_public_channels("team1", per_page=200)

    assert len(result) == 200 * 8 + 1
    assert seen == list(range(9))


def test_pagination_stops_at_the_safety_limit(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[channel(f"c{i}") for i in range(5)])

    with build_client(handler) as time:
        result = time.list_public_channels("team1", per_page=5, max_pages=3)

    assert len(result) == 15


def test_list_teams():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v4/users/me/teams"
        return httpx.Response(200, json=[TEAM])

    with build_client(handler) as time:
        assert [t["name"] for t in time.list_teams()] == ["tsentralnyy-universitet"]


# --------------------------------------------------------------------------- #
# Хранилище выбора
# --------------------------------------------------------------------------- #


@pytest.fixture()
def store(tmp_path: Path):
    from .conftest import time_state

    return time_state.Store(tmp_path / "state.json")


def selection(name: str = "anonsy-tsu"):
    from .conftest import time_state

    return time_state.Selection(team="tsentralnyy-universitet", channel=name, display_name="Анонсы")


def test_add_and_read_back(store):
    assert store.add(selection()) is True
    assert [s.channel for s in store.selected()] == ["anonsy-tsu"]
    assert store.is_selected("tsentralnyy-universitet", "anonsy-tsu")


def test_adding_twice_is_a_noop(store):
    store.add(selection())
    assert store.add(selection()) is False
    assert len(store.selected()) == 1


def test_remove(store):
    store.add(selection())
    assert store.remove("tsentralnyy-universitet", "anonsy-tsu") is True
    assert store.selected() == []
    assert store.remove("tsentralnyy-universitet", "anonsy-tsu") is False


def test_selection_survives_a_restart(store, tmp_path):
    from .conftest import time_state

    store.add(selection())
    reopened = time_state.Store(tmp_path / "state.json")
    assert [s.channel for s in reopened.selected()] == ["anonsy-tsu"]


def test_slug_matches_what_the_parser_sends(store):
    assert selection().slug == "time-tsentralnyy-universitet-anonsy-tsu"


def test_seed_only_fills_an_empty_selection(store):
    """Иначе рестарт контейнера откатывал бы всё, что настроили руками."""

    store.add(selection("chosen-by-hand"))
    store.seed([selection("from-env")])
    assert [s.channel for s in store.selected()] == ["chosen-by-hand"]


def test_seed_works_when_nothing_is_selected(store):
    store.seed([selection("from-env")])
    assert [s.channel for s in store.selected()] == ["from-env"]


def test_replace_all_swaps_the_whole_set(store):
    store.add(selection("a"))
    store.replace_all([selection("b"), selection("c")])
    assert sorted(s.channel for s in store.selected()) == ["b", "c"]


def test_run_results_are_recorded_and_pruned(store):
    from .conftest import time_state

    store.add(selection())
    store.record_run(
        "tsentralnyy-universitet", "anonsy-tsu", time_state.RunResult(created=25, skipped=35)
    )
    assert store.runs()["tsentralnyy-universitet/anonsy-tsu"].created == 25

    store.remove("tsentralnyy-universitet", "anonsy-tsu")
    assert store.runs() == {}


def test_corrupted_state_file_does_not_crash(tmp_path):
    from .conftest import time_state

    path = tmp_path / "state.json"
    path.write_text("{ это не json", encoding="utf-8")
    assert time_state.Store(path).selected() == []


def test_state_file_is_readable_json(store, tmp_path):
    store.add(selection())
    data = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert data["selected"][0]["channel"] == "anonsy-tsu"


# --------------------------------------------------------------------------- #
# Права автора: кто вообще может писать новости
# --------------------------------------------------------------------------- #


def test_plain_member_cannot_post_news():
    """Студент в чате потока задаёт вопросы, а не публикует объявления."""

    assert not client_module.has_posting_privileges({"channel_user"})


def test_guest_is_not_privileged():
    assert not client_module.has_posting_privileges({"channel_user", "channel_guest"})


def test_channel_admin_is_privileged():
    """Куратор в чате потока — у него `channel_admin`."""

    assert client_module.has_posting_privileges({"channel_user", "channel_admin"})


def test_custom_scheme_roles_are_privileged():
    """В «Анонсах ЦУ» своя схема прав, и роли там названы её идентификаторами.

    Проверка на `channel_admin` выкосила бы весь новостной канал: этой роли
    там нет ни у кого. Значим не ярлык, а то, что права шире обычных.
    """

    roles = {"i4pqautcx7ys8g5akin3ibeh1y", "usdnk4tu9bgh7e83e816n3qssa"}
    assert client_module.has_posting_privileges(roles)


def test_no_roles_at_all_is_not_privileged():
    assert not client_module.has_posting_privileges(set())


def test_roles_lookup_survives_a_departed_author():
    """Автор мог выйти из канала — это не повод ронять весь проход."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    with build_client(handler) as time:
        assert time.channel_member_roles("chan1", "gone") == set()


def test_roles_lookup_parses_the_space_separated_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"roles": "channel_user channel_admin"})

    with build_client(handler) as time:
        assert time.channel_member_roles("chan1", "u1") == {"channel_user", "channel_admin"}


def test_authors_mode_defaults_to_privileged(store):
    store.add(selection())
    assert store.selected()[0].authors == "privileged"


def test_authors_mode_is_per_channel(store):
    """В одном канале объявления пишут кураторы, в другом — обычный участник."""

    store.add(selection("chat"))
    store.add(selection("broadcast"))
    assert store.set_authors("tsentralnyy-universitet", "broadcast", "all") is True

    modes = {s.channel: s.authors for s in store.selected()}
    assert modes == {"chat": "privileged", "broadcast": "all"}


def test_authors_mode_survives_a_restart(store, tmp_path):
    from .conftest import time_state

    store.add(selection())
    store.set_authors("tsentralnyy-universitet", "anonsy-tsu", "all")
    reopened = time_state.Store(tmp_path / "state.json")
    assert reopened.selected()[0].authors == "all"


def test_setting_authors_on_an_unselected_channel_reports_failure(store):
    assert store.set_authors("tsentralnyy-universitet", "nope", "all") is False
