"""Поиск перепечаток в корпусе: `tools/corpus/duplicates.py`."""

from __future__ import annotations

from tools.corpus.duplicates import (
    copy_pairs,
    event_dates,
    find_groups,
    from_record,
    normalize,
    same_event,
    similarity,
    shingles,
)


def copy_ids(groups):
    return [copy for copy, _, _ in copy_pairs(groups)]

LIFTS = (
    "Будь в курсе. Во вторник, {date} с 06:00 до 09:00 в кампусе Центрального "
    "Университета будут проводиться работы по техническому обслуживанию лифтов "
    "с их поочередным временным отключением. Просьба пользоваться лестницами."
)
CLEANING = (
    "{prefix} В ночь с 19 на 20 июня в кампусе ЦУ будет генеральная уборка. "
    "Заберите личные вещи из гардероба на 1 этаже и раздевалок спортзала "
    "не позднее 22:00 19 июня. Оставленные вещи будут утилизированы."
)


def post(id, text, channel="a", published_at="2026-01-01T00:00:00+00:00"):
    return from_record(
        {"id": id, "source_key": channel, "published_at": published_at, "body_md": text}
    )


def test_normalize_drops_emoji_codes_links_and_markup():
    assert normalize("**Будь в курсе** :cu_black_lightning: https://t.me/x @all") == "будь в курсе"


def test_similarity_ignores_a_different_prefix():
    left = shingles(CLEANING.format(prefix="Будь в курсе."))
    right = shingles(CLEANING.format(prefix="Напоминаем:"))
    assert similarity(left, right) > 0.8


def test_event_dates_reads_both_ends_of_a_range_and_numeric_dates():
    assert event_dates("В ночь с 19 на 20 июня") == frozenset({(19, 6), (20, 6)})
    assert event_dates("выбор курсов закрывается 03.09 в 14:00") == frozenset({(3, 9)})
    assert event_dates("Кампус работает с 08:00 до 22:00") == frozenset()


def test_same_event_needs_a_shared_date_only_when_both_have_dates():
    assert same_event(frozenset(), frozenset({(1, 9)}))
    assert same_event(frozenset({(1, 9), (2, 9)}), frozenset({(2, 9)}))
    assert not same_event(frozenset({(24, 3)}), frozenset({(21, 7)}))


def test_same_text_in_several_channels_becomes_one_group():
    text = "Срок оплаты обучения — до 15 сентября. Квитанции высланы на почту ЦУ."
    posts = [
        post("a1", text, "swe", "2026-08-25T10:00:00+00:00"),
        post("a2", text, "ai", "2026-08-25T11:00:00+00:00"),
        post("a3", text, "business", "2026-08-26T09:00:00+00:00"),
    ]

    groups = find_groups(posts)

    assert len(groups) == 1
    assert groups[0].origin.id == "a1"  # самый ранний
    assert copy_ids(groups) == ["a2", "a3"]
    assert groups[0].channels == ["ai", "business", "swe"]


def test_copy_pairs_keep_the_channel_of_every_copy():
    """Направление копии берётся из её канала, поэтому канал нельзя терять."""

    text = "Срок оплаты обучения — до 15 сентября."
    posts = [
        post("a1", text, "swe", "2026-08-25T10:00:00+00:00"),
        post("a2", text, "ai", "2026-08-25T11:00:00+00:00"),
    ]

    assert copy_pairs(find_groups(posts)) == [("a2", "a1", "ai")]


def test_announcement_and_its_reminder_are_one_group():
    posts = [
        post("a1", CLEANING.format(prefix="Будь в курсе."), "ts", "2026-06-16T08:00:00+00:00"),
        post("a2", CLEANING.format(prefix="Напоминаем:"), "ts", "2026-06-19T08:00:00+00:00"),
    ]

    assert copy_ids(find_groups(posts)) == ["a2"]


def test_same_template_with_different_dates_stays_apart():
    posts = [
        post("a1", LIFTS.format(date="24 марта,"), "ts", "2026-03-23T08:00:00+00:00"),
        post("a2", LIFTS.format(date="21 июля,"), "ts", "2026-07-20T08:00:00+00:00"),
    ]

    assert find_groups(posts) == []


def test_unrelated_posts_and_short_replies_produce_nothing():
    posts = [
        post("a1", "Зал сегодня работает?"),
        post("a2", "Добрый день, не выставили посещение"),
        post("a3", "8 этаж закрыт под мероприятие, пользуйтесь другими пространствами"),
    ]

    assert find_groups(posts) == []


def test_threshold_controls_how_close_texts_must_be():
    posts = [
        post("a1", "Кураторский час сегодня в 12:00, будет запись встречи", "swe"),
        post("a2", "Кураторский час сегодня в 12:00, запись встречи будет позже", "ai"),
    ]

    assert find_groups(posts, threshold=0.95) == []
    assert copy_ids(find_groups(posts, threshold=0.3)) == ["a2"]
