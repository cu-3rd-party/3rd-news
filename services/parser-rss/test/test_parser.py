from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from thirdnews_contracts import AttachmentKind

from lib.domain.entities.feed_source import FeedSource
from lib.infra.storage.memory_health import MemoryHealthStorage
from lib.interactor.use_cases.parse_feed import clean_markup, parse_feeds, to_submission


def entry(**overrides):
    values = {
        "id": "urn:item:1",
        "link": "https://example.test/news/1",
        "title": "Новость",
        "summary": "<p>Основной <b>текст</b></p>",
        "content": [],
        "enclosures": [],
        "published_parsed": None,
        "updated_parsed": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_active_html_is_removed_but_text_is_preserved() -> None:
    value = clean_markup(
        "<p>Hello &amp; world</p><script>alert(1)</script><iframe src='x'>bad</iframe>"
    )
    assert value == "Hello & world"


def test_feed_configuration_requires_explicit_source_and_url() -> None:
    assert parse_feeds("campus|https://example.test/rss, broken, other|https://x.test") == [
        FeedSource("campus", "https://example.test/rss"),
        FeedSource("other", "https://x.test"),
    ]


def test_readiness_tracks_the_last_complete_poll_cycle() -> None:
    health = MemoryHealthStorage()
    assert health.ready is False
    health.record_cycle(True)
    assert health.ready is True
    health.record_cycle(False)
    assert health.ready is False


def test_entry_maps_stable_identity_content_and_source() -> None:
    item = to_submission("campus", entry(), max_age_days=30)
    assert item is not None
    assert (item.source, item.external_id) == ("campus", "urn:item:1")
    assert item.body_md == "Основной текст"
    assert str(item.source_link) == "https://example.test/news/1"
    assert item.extra == {"parser": "rss"}


def test_content_body_wins_over_summary() -> None:
    item = to_submission(
        "campus",
        entry(content=[SimpleNamespace(value="<p>Полный текст</p>")]),
        max_age_days=30,
    )
    assert item is not None and item.body_md == "Полный текст"


def test_missing_identity_or_empty_content_is_skipped() -> None:
    assert to_submission("campus", entry(id=None, link=None), max_age_days=30) is None
    assert to_submission("campus", entry(summary="", title=""), max_age_days=30) is None


def test_old_entries_respect_configured_age_window() -> None:
    old = datetime.now(UTC) - timedelta(days=20)
    item = entry(published_parsed=old.timetuple())
    assert to_submission("campus", item, max_age_days=10) is None
    assert to_submission("campus", item, max_age_days=30) is not None


def test_enclosures_become_typed_remote_attachments() -> None:
    item = to_submission(
        "campus",
        entry(
            enclosures=[
                {"href": "https://example.test/poster.png", "type": "image/png"},
                {"href": "https://example.test/talk.mp3", "type": "audio/mpeg"},
                {"href": "https://example.test/guide.pdf", "type": "application/pdf"},
                {"type": "video/mp4"},
            ]
        ),
        max_age_days=30,
    )
    assert item is not None
    assert [attachment.kind for attachment in item.attachments] == [
        AttachmentKind.IMAGE,
        AttachmentKind.AUDIO,
        AttachmentKind.PDF,
    ]
