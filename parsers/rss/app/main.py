"""RSS/Atom parser — a working example of a parser microservice.

It owns no state: `external_id` makes ingestion idempotent, so re-reading a
feed from the beginning costs one request and changes nothing. Copy this file
as the starting point for a Telegram, VK or site-scraping parser.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import feedparser
from thirdnews_contracts import (
    AttachmentInput,
    AttachmentKind,
    IngestClient,
    IngestError,
    NewsSubmission,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("3rdnews.parser.rss")

NEWS_URL = os.getenv("NEWS_URL", "http://main:8000")
API_KEY = os.getenv("NEWS_API_KEY", "")
#: `slug|url` pairs, comma-separated: "univ-main|https://example.edu/feed.xml"
FEEDS = os.getenv("FEEDS", "")
INTERVAL_S = int(os.getenv("POLL_INTERVAL_S", "600"))
#: Items older than this are ignored on the first run of a new feed.
MAX_AGE_DAYS = int(os.getenv("MAX_AGE_DAYS", "30"))


def parse_feeds(spec: str) -> list[tuple[str, str]]:
    feeds: list[tuple[str, str]] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        slug, _, url = chunk.partition("|")
        if not url:
            logger.warning("skipping malformed feed spec %r, expected 'slug|url'", chunk)
            continue
        feeds.append((slug.strip(), url.strip()))
    return feeds


def _published(entry) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        value = getattr(entry, field, None)
        if value:
            return datetime.fromtimestamp(time.mktime(value), tz=timezone.utc)
    return None


def _body(entry) -> str:
    if getattr(entry, "content", None):
        return entry.content[0].value
    return getattr(entry, "summary", "") or getattr(entry, "title", "")


def _attachments(entry) -> list[AttachmentInput]:
    attachments: list[AttachmentInput] = []
    for enclosure in getattr(entry, "enclosures", []) or []:
        url = enclosure.get("href")
        if not url:
            continue
        mime = enclosure.get("type", "")
        kind = AttachmentKind.FILE
        if mime.startswith("image/"):
            kind = AttachmentKind.IMAGE
        elif mime.startswith("video/"):
            kind = AttachmentKind.VIDEO
        elif mime == "application/pdf":
            kind = AttachmentKind.PDF
        attachments.append(AttachmentInput(kind=kind, url=url, mime=mime or None))
    return attachments


def to_submission(slug: str, entry) -> NewsSubmission | None:
    published = _published(entry)
    if published and (datetime.now(timezone.utc) - published).days > MAX_AGE_DAYS:
        return None

    external_id = getattr(entry, "id", None) or getattr(entry, "link", None)
    if not external_id:
        # Without a stable id we cannot dedup, and re-posting on every poll is
        # worse than skipping the item.
        return None

    return NewsSubmission(
        external_id=str(external_id),
        source_key=slug,
        title=getattr(entry, "title", None),
        body_md=_body(entry),
        source_link=getattr(entry, "link", None),
        published_at=published,
        attachments=_attachments(entry),
        extra={"parser": "rss"},
    )


def poll_once(client: IngestClient, feeds: list[tuple[str, str]]) -> None:
    for slug, url in feeds:
        try:
            parsed = feedparser.parse(url)
        except Exception:  # noqa: BLE001 - a broken feed must not stop the others
            logger.exception("failed to fetch %s", url)
            continue

        created = duplicates = skipped = 0
        for entry in parsed.entries:
            submission = to_submission(slug, entry)
            if submission is None:
                skipped += 1
                continue
            try:
                result = client.submit(submission)
            except IngestError:
                logger.exception("failed to submit an item from %s", url)
                continue
            if result.status.value == "created":
                created += 1
            else:
                duplicates += 1
        logger.info(
            "%s: %d new, %d already known, %d skipped", slug, created, duplicates, skipped
        )


def main() -> None:
    if not API_KEY:
        raise SystemExit("NEWS_API_KEY is required (create an ingest key in the admin)")
    feeds = parse_feeds(FEEDS)
    if not feeds:
        raise SystemExit("FEEDS is empty; expected 'slug|url,slug|url'")

    client = IngestClient(NEWS_URL, API_KEY)
    logger.info("polling %d feed(s) every %ds", len(feeds), INTERVAL_S)
    while True:
        poll_once(client, feeds)
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
