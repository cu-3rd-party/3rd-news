"""Скрипты подготовки корпуса: отсев реплик, копирование меток, отбор набора."""

from __future__ import annotations

from tools.corpus.copy_labels import manual_labels, plan_transfers
from tools.corpus.reject_noise import broadcasters, find_candidates, reasons_to_reject
from tools.corpus.sample import candidates, pick, quotas

ANNOUNCEMENT = (
    "**Оплата обучения**\n\nНапоминаем, что срок оплаты обучения — до 15 сентября. "
    "Всем студентам на почту ЦУ высланы квитанции с индивидуальным QR."
)


def item(id, body, channel="sport", author="Студент", **extra):
    return {
        "id": id,
        "body_md": body,
        "title": None,
        "source_key": channel,
        "published_at": f"2026-06-{int(id[-1]) + 1:02d}T10:00:00+00:00",
        "extra": {"author": author},
        "status": "published",
        "manual_facets": [],
        "effective": {},
        **extra,
    }


# --- отсев реплик ---------------------------------------------------------- #


def test_broadcasters_are_the_authors_who_post_regularly():
    items = [item(f"a{i}", "…", author="Куратор") for i in range(5)]
    items.append(item("b1", "…", author="Студент"))

    assert ("sport", "Куратор") in broadcasters(items)
    assert ("sport", "Студент") not in broadcasters(items)


def test_a_students_question_is_a_candidate():
    regulars = {("sport", "Куратор")}

    reasons = reasons_to_reject(item("a1", "Здравствуйте, зал сегодня работает?"), regulars)

    assert reasons and "автор не ведёт этот канал" in reasons


def test_curator_announcements_survive_every_check():
    regulars = {("sport", "Куратор")}

    assert reasons_to_reject(item("a1", ANNOUNCEMENT, author="Куратор"), regulars) == ()
    # Даже короткое сообщение куратора остаётся: автор ведёт канал.
    assert reasons_to_reject(item("a2", "Зал закрыт до 15:00", author="Куратор"), regulars) == ()


def test_length_markup_links_and_mentions_each_save_a_post():
    regulars: set[tuple[str, str]] = set()

    assert reasons_to_reject(item("a1", "Привет! " * 40), regulars) == ()
    assert reasons_to_reject(item("a2", "**Внимание** зал закрыт"), regulars) == ()
    assert reasons_to_reject(item("a3", "запись тут https://t.me/x"), regulars) == ()
    assert reasons_to_reject(item("a4", "Зал закрыт @all"), regulars) == ()


def test_find_candidates_uses_per_channel_authorship():
    items = [item(f"a{i}", "объявление " * 3, channel="sport", author="Куратор") for i in range(5)]
    items.append(item("b1", "а когда пересдача?", channel="sport", author="Студент"))
    items.append(item("c1", "а когда пересдача?", channel="dm", author="Куратор"))

    found = {candidate.id for candidate in find_candidates(items)}

    # Тот же автор в другом канале ничего не ведёт, поэтому его реплика — шум.
    assert found == {"b1", "c1"}


# --- копирование меток ----------------------------------------------------- #


def test_manual_labels_skip_the_source_driven_axis():
    news = {
        "manual_facets": ["topic", "program"],
        "effective": {"topic": ["docs"], "program": ["ai-2025"], "action": ["deadline"]},
    }

    assert manual_labels(news) == {"topic": ["docs"]}


def test_labels_travel_from_the_origin_to_every_copy():
    origin = item("a1", ANNOUNCEMENT, channel="swe")
    origin["manual_facets"] = ["topic", "action"]
    origin["effective"] = {"topic": ["docs"], "action": ["deadline"], "program": ["swe-2025"]}
    copies = [item("a2", ANNOUNCEMENT, channel="ai"), item("a3", ANNOUNCEMENT, channel="business")]

    transfers = plan_transfers([origin, *copies])

    assert {t.target_id for t in transfers} == {"a2", "a3"}
    assert all(t.origin_id == "a1" for t in transfers)
    assert transfers[0].labels == {"topic": ["docs"], "action": ["deadline"]}
    assert "program" not in transfers[0].labels


def test_a_copy_already_labelled_by_hand_is_left_alone():
    origin = item("a1", ANNOUNCEMENT, channel="swe")
    origin["manual_facets"] = ["topic"]
    origin["effective"] = {"topic": ["docs"]}
    copy = item("a2", ANNOUNCEMENT, channel="ai")
    copy["manual_facets"] = ["topic"]
    copy["effective"] = {"topic": ["study"]}

    assert plan_transfers([origin, copy]) == []


def test_nothing_to_copy_when_the_origin_is_unlabelled():
    posts = [item("a1", ANNOUNCEMENT, channel="swe"), item("a2", ANNOUNCEMENT, channel="ai")]

    assert plan_transfers(posts) == []


# --- отбор набора ---------------------------------------------------------- #


def test_quotas_cap_the_dominant_channel():
    share = quotas({"big": 5000, "a": 300, "b": 300, "c": 300, "d": 300}, size=100, cap=0.2)

    assert sum(share.values()) == 100
    assert share["big"] == 20  # потолок, а не 78
    assert all(share[key] >= 1 for key in "abcd")


def test_cap_rises_when_too_few_channels_to_fill_the_sample():
    """Потолок против перекоса, но набор важнее: 20% × 3 канала — это не 100."""

    share = quotas({"big": 500, "small": 100, "tiny": 20}, size=100, cap=0.2)

    assert sum(share.values()) == 100
    assert share["tiny"] == 20  # исчерпан целиком
    assert share["big"] > 20  # потолок пришлось поднять


def test_quotas_never_ask_for_more_than_a_channel_has():
    share = quotas({"a": 3, "b": 3}, size=100, cap=1.0)

    assert share == {"a": 3, "b": 3}


def test_quotas_handle_an_empty_corpus():
    assert quotas({}, size=10) == {}
    assert quotas({"a": 5}, size=0) == {}


def test_candidates_drop_rejected_posts_and_copies():
    origin = item("a1", ANNOUNCEMENT, channel="swe")
    copy = item("a2", ANNOUNCEMENT, channel="ai")
    noise = item("a3", "вопрос", channel="sport", status="rejected")
    other = item("a4", "Экзамен по дискретной математике пройдёт 15 июня в кампусе, устно.")

    left = {news["id"] for news in candidates([origin, copy, noise, other])}

    assert left == {"a1", "a4"}


def test_pick_is_deterministic_and_respects_the_quota():
    pool = [item(f"a{i}", f"объявление номер {i} " * 5, channel="big") for i in range(50)]
    pool += [item(f"b{i}", f"другое объявление {i} " * 5, channel="small") for i in range(10)]

    first = pick(pool, size=20, seed=7)
    again = pick(pool, size=20, seed=7)

    assert [news["id"] for news in first] == [news["id"] for news in again]
    assert len(first) == 20
    assert len({news["id"] for news in first}) == 20


# --- снятие ручных меток с осей от источника ------------------------------- #


def test_pinned_finds_only_posts_with_a_manual_label_on_that_facet():
    from tools.corpus.release_facet import pinned

    posts = [
        {"id": "a1", "manual_facets": ["topic", "program"]},
        {"id": "a2", "manual_facets": ["topic"]},
        {"id": "a3", "manual_facets": []},
        {"id": "a4"},
    ]

    assert [item["id"] for item in pinned(posts, "program")] == ["a1"]


# --- прогресс разметки ------------------------------------------------------ #


def test_progress_counts_manual_labels_and_ignores_source_driven_axes():
    from tools.corpus.progress import human_facets, labelled

    facets = human_facets({"program"})

    assert "program" not in facets
    assert {"topic", "action", "importance", "audience"} <= set(facets)
    # Метка от источника разметкой не считается.
    news = {"manual_facets": ["topic", "program"]}
    assert labelled(news, facets) == {"topic"}


def test_progress_report_says_how_much_is_done():
    from tools.corpus.progress import report

    full = ["topic", "action", "importance", "audience"]
    items = [
        {**item("a1", ANNOUNCEMENT, channel="swe"), "manual_facets": full},
        {**item("a2", "Экзамен 15 июня, устно, в кампусе", channel="ai"), "manual_facets": ["topic"]},
        {**item("a3", "Лекция про кванты 26 мая в аудитории", channel="ai")},
    ]
    sources = [{"default_labels": {"program": ["ai-2025"]}}]

    text = report(items, sources, size=10)

    assert "размечено полностью: 1 из 10" in text
    assert "начато, но не дозакрыто: 1" in text


def test_pick_keeps_already_labelled_posts_in_the_plan():
    """Смена размера набора не должна выбрасывать сделанную разметку."""

    pool = [item(f"a{i}", f"объявление номер {i} " * 5, channel="big") for i in range(40)]
    pool += [item(f"b{i}", f"другое объявление {i} " * 5, channel="small") for i in range(10)]
    keep = frozenset({"a37", "b9"})

    chosen = {news["id"] for news in pick(pool, size=10, seed=3, keep=keep)}

    assert keep <= chosen
    assert len(chosen) == 10


def test_kept_posts_take_up_their_channel_quota():
    pool = [item(f"a{i}", f"объявление номер {i} " * 5, channel="one") for i in range(20)]
    keep = frozenset({f"a{i}" for i in range(5)})

    chosen = pick(pool, size=5, seed=1, keep=keep)

    assert {news["id"] for news in chosen} == keep


# --- флаг золота ------------------------------------------------------------ #


def test_gold_lists_only_frozen_posts():
    from tools.corpus.gold import describe, golden

    posts = [
        {**item("a1", ANNOUNCEMENT, channel="swe"), "is_gold": True},
        {**item("a2", ANNOUNCEMENT, channel="ai"), "is_gold": True},
        item("a3", ANNOUNCEMENT, channel="ai"),
    ]

    assert [news["id"] for news in golden(posts)] == ["a1", "a2"]
    assert "золотых постов: 2" in describe(posts)
    assert describe([item("a4", ANNOUNCEMENT)]) == "золотых постов нет"
